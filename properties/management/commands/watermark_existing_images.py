import os
from PIL import Image, ImageDraw, ImageFont
from io import BytesIO
from django.core.management.base import BaseCommand
from django.core.files.base import ContentFile
from properties.models import PropertyImage

class Command(BaseCommand):
    help = 'Apply watermark to all existing property images'

    def handle(self, *args, **options):
        images = PropertyImage.objects.all()
        self.stdout.write(f"Found {images.count()} images to process.")
        count = 0
        for img_obj in images:
            try:
                img = Image.open(img_obj.image)
                width, height = img.size
                draw = ImageDraw.Draw(img)
                font_size = int(min(width, height) * 0.04)
                try:
                    font = ImageFont.truetype("arial.ttf", font_size)
                except:
                    font = ImageFont.load_default()
                text = "RentSure Kenya"
                bbox = draw.textbbox((0, 0), text, font=font)
                textwidth = bbox[2] - bbox[0]
                textheight = bbox[3] - bbox[1]
                x = width - textwidth - 10
                y = height - textheight - 10
                draw.text((x, y), text, fill=(255, 255, 255, 128), font=font)
                output = BytesIO()
                img.save(output, format='JPEG', quality=90)
                output.seek(0)
                # Save over the existing file
                img_obj.image.save(
                    os.path.basename(img_obj.image.name),
                    ContentFile(output.read()),
                    save=True
                )
                count += 1
                self.stdout.write(f"Processed {count}: {img_obj.image.name}")
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"Failed on {img_obj.id}: {e}"))
        self.stdout.write(self.style.SUCCESS(f"Done. Watermarked {count} images."))