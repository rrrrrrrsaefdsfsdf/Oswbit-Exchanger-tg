import random
import string
import io
from typing import Tuple
from captcha.image import ImageCaptcha

class CaptchaGenerator:



    @staticmethod
    def generate_image_captcha() -> Tuple[io.BytesIO, str]:
        """Генерация капчи с картинкой"""
        text = ''.join(random.choices(string.ascii_uppercase + string.digits, k=5))
        
        image = ImageCaptcha(width=200, height=80, fonts=['arial.ttf'])
        
        data = image.generate(text)
        
        image_buffer = io.BytesIO()
        image_buffer.write(data.read())
        image_buffer.seek(0)
        
        return image_buffer, text
