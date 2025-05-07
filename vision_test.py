import io
import os
from google.cloud import vision

def detect_web_references(image_path):
    """Detects web references to an image."""
    client = vision.ImageAnnotatorClient()

    # Expand the tilde to the user's home directory
    expanded_path = os.path.expanduser(image_path)

    try:
        with io.open(expanded_path, 'rb') as image_file:
            content = image_file.read()
        image = vision.Image(content=content)

        print(f"正在分析图片: {expanded_path}")
        response = client.web_detection(image=image)
        annotations = response.web_detection

        if response.error.message:
            print(f"API返回错误: {response.error.message}")
            return

        print("\n--- Web Entities ---")
        if annotations.web_entities:
            for entity in annotations.web_entities:
                print(f"  描述: {entity.description}, Score: {entity.score:.4f}")
        else:
            print("  未找到Web Entities。")

        print("\n--- Pages with Matching Images ---")
        if annotations.pages_with_matching_images:
            for page in annotations.pages_with_matching_images:
                print(f"  页面URL: {page.url}")
                if page.page_title:
                    print(f"    页面标题: {page.page_title.strip()}")
                if page.full_matching_images:
                    print(f"    包含 {len(page.full_matching_images)} 个完全匹配的图片。")
                if page.partial_matching_images:
                    print(f"    包含 {len(page.partial_matching_images)} 个部分匹配的图片。")
        else:
            print("  未找到包含匹配图片的页面。")

        print("\n--- Full Matching Images (来自网络的独立图片链接) ---")
        if annotations.full_matching_images:
            for image_match in annotations.full_matching_images:
                print(f"  图片URL: {image_match.url}")
        else:
            print("  未找到完全匹配的图片。")

        print("\n--- Partial Matching Images (来自网络的独立图片链接) ---")
        if annotations.partial_matching_images:
            for image_match in annotations.partial_matching_images:
                print(f"  图片URL: {image_match.url}")
        else:
            print("  未找到部分匹配的图片。")

        print("\n--- Visually Similar Images (来自网络的独立图片链接) ---")
        if annotations.visually_similar_images:
            for image_match in annotations.visually_similar_images:
                print(f"  图片URL: {image_match.url}")
        else:
            print("  未找到视觉上相似的图片。")

    except Exception as e:
        print(f"执行脚本时发生错误 (路径: {expanded_path}): {e}")

if __name__ == '__main__':
    # 请将这里的路径替换为您测试图片的实际路径
    # Windows路径示例: r"C:\Users\YourUser\Pictures\test_image.png"
    # (注意路径字符串前的 'r'，或者使用双反斜杠 '\\' )
    test_image_file_path = "~/1.png" # <--- 这是您的图片路径

    # 直接调用函数，移除了之前的if判断
    detect_web_references(test_image_file_path)