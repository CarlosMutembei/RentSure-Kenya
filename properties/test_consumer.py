from channels.generic.websocket import AsyncWebsocketConsumer

class TestConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        await self.accept()
        await self.send(text_data="Connected to test WebSocket")
    
    async def receive(self, text_data):
        await self.send(text_data=f"Echo: {text_data}")