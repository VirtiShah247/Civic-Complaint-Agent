from PIL import Image, ImageDraw
from pathlib import Path

def create_sample_image(filepath: str, label: str = "Civic Issue Sample"):
    """Create a sample synthetic test image."""
    img = Image.new("RGB", (400, 300), color=(160, 160, 160))
    d = ImageDraw.Draw(img)
    d.rectangle([(80, 80), (320, 220)], fill=(60, 60, 60))
    d.text((100, 140), label, fill=(255, 255, 255))
    
    Path(filepath).parent.mkdir(parents=True, exist_ok=True)
    img.save(filepath, "JPEG")
    print(f"Sample test image saved: {filepath}")

if __name__ == "__main__":
    create_sample_image("data/samples/sample_pothole.jpg", "Pothole on Asphalt Road")
    create_sample_image("data/samples/sample_garbage.jpg", "Overflowing Street Garbage Bin")
