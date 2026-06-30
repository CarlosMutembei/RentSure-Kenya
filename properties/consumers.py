import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.contrib.auth import get_user_model
from django.utils import timezone

User = get_user_model()
from .models import ChatMessage, Property

class ChatConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        print("=== ChatConsumer connect called ===")
        # Initialize attributes to None immediately so disconnect can never crash
        self.personal_group_name = None
        self.room_group_name = None
        
        self.property_id = self.scope['url_route']['kwargs']['property_id']
        self.other_user_id = self.scope['url_route']['kwargs']['other_user_id']
        self.user = self.scope['user']

        # Guard against unauthenticated users early before adding to layers
        if not self.user or not self.user.is_authenticated:
            print("User not authenticated – closing hook handshake")
            await self.close(code=4003)
            return

        self.personal_group_name = f"user_{self.user.id}"
        await self.channel_layer.group_add(self.personal_group_name, self.channel_name)
        print(f"Property: {self.property_id}, other: {self.other_user_id}, User: {self.user}")

        # Derive consistent deterministic room names via sorted integers
        try:
            ids = sorted([self.user.id, int(self.other_user_id)])
            self.room_name = f"chat_{ids[0]}_{ids[1]}_{self.property_id}"
            self.room_group_name = self.room_name
        except (ValueError, TypeError):
            print("Invalid other_user_id format provided – closing hook handshake")
            await self.close(code=4040)
            return

        await self.channel_layer.group_add(self.room_group_name, self.channel_name)
        await self.accept()
        print("WebSocket accepted successfully")

    async def disconnect(self, close_code):
        print(f"Disconnected with code {close_code}")
        
        # Defensive cleanup checks protect against unassigned variables
        if getattr(self, 'room_group_name', None):
            await self.channel_layer.group_discard(self.room_group_name, self.channel_name)
            
        if getattr(self, 'personal_group_name', None):
            await self.channel_layer.group_discard(self.personal_group_name, self.channel_name)

    async def receive(self, text_data):
        print("Received message data payload:", text_data)
        try:
            text_data_json = json.loads(text_data)
            message = text_data_json['message']
        except (json.JSONDecodeError, KeyError):
            return

        # Optimization: Create timestamp instantly in memory (saves a DB worker context switch)
        timestamp_str = timezone.localtime(timezone.now()).strftime("%H:%M, %b %d")

        # Save record asynchronously
        await self.save_message(message)

        # Broadcast payload down to the active conversation room matrix
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'chat_message',
                'message': message,
                'sender_id': self.user.id,
                'sender_username': self.user.username,
                'timestamp': timestamp_str,
            }
        )

        # Notify the target recipient seamlessly if they're on a different account
        if self.user.id != int(self.other_user_id):
            property_obj = await self.get_property()
            if property_obj:
                await self.channel_layer.group_send(
                    f"user_{self.other_user_id}",
                    {
                        'type': 'new_message_notification',
                        'sender': self.user.username,
                        'property_title': property_obj.title,
                        'property_id': self.property_id,
                    }
                )

    async def chat_message(self, event):
        await self.send(text_data=json.dumps({
            'message': event['message'],
            'sender_id': event['sender_id'],
            'sender_username': event['sender_username'],
            'timestamp': event['timestamp'],
        }))

    @database_sync_to_async
    def save_message(self, message):
        try:
            property_obj = Property.objects.get(id=self.property_id)
            other_user = User.objects.get(id=self.other_user_id)
            msg = ChatMessage.objects.create(
                sender=self.user,
                receiver=other_user,
                property=property_obj,
                message=message
            )
            print(f"Message persisted directly to database, ID={msg.id}")
            return True
        except (Property.DoesNotExist, User.DoesNotExist) as e:
            print(f"Database write abort: Linked entities not found. Exception: {e}")
            return False

    @database_sync_to_async
    def get_property(self):
        try:
            return Property.objects.get(id=self.property_id)
        except Property.DoesNotExist:
            return None


class NotificationConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.personal_group_name = None
        self.user = self.scope['user']
        
        if not self.user or not self.user.is_authenticated:
            await self.close(code=4003)
            return
            
        self.personal_group_name = f"user_{self.user.id}"
        await self.channel_layer.group_add(self.personal_group_name, self.channel_name)
        await self.accept()
        print(f"Notification pipeline established securely for client: {self.user.username}")

    async def disconnect(self, close_code):
        if getattr(self, 'personal_group_name', None):
            await self.channel_layer.group_discard(self.personal_group_name, self.channel_name)

    async def new_message_notification(self, event):
        await self.send(text_data=json.dumps({
            'type': 'new_message',
            'sender': event['sender'],
            'property_title': event['property_title'],
            'property_id': event['property_id'],
        }))