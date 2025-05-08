import pyautogui
import openai
import base64
import os
import time
import re # 导入正则表达式模块
import webbrowser # 导入webbrowser模块
from dotenv import load_dotenv

# 加载 .env 文件中的环境变量
load_dotenv()

# 从环境变量中获取 OpenAI API Key
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    print("错误：请确保 .env 文件中已设置 OPENAI_API_KEY")
    exit()

client = openai.OpenAI(api_key=OPENAI_API_KEY)

# 全局变量，用于模板图片名称
CAMERA_ICON_TEMPLATE_PATH = "camera_icon_template.png"
UPLOAD_BUTTON_TEMPLATE_PATH = "upload_button_template.png" # 新增上传按钮模板路径
# 将使用 data 目录下的 github.png
YOUR_IMAGE_TO_UPLOAD_PATH = os.path.join("data", "github.png") 

def capture_and_encode_screenshot(filename="screenshot.png", use_manual_file=None, for_ai_analysis=True):
    """
    捕获全屏截图或加载指定文件。
    如果 for_ai_analysis 为 True, 则编码为 Base64 字符串并返回。
    如果 for_ai_analysis 为 False, 则只保存文件并返回文件名 (主要用于pyautogui图像识别前的准备，虽然pyautogui可以直接操作屏幕)。
    """
    try:
        if use_manual_file:
            if os.path.exists(use_manual_file):
                print(f"正在加载手动提供的截图: {use_manual_file}")
                if for_ai_analysis:
                    with open(use_manual_file, "rb") as image_file:
                        return base64.b64encode(image_file.read()).decode('utf-8')
                else:
                    return use_manual_file # 返回文件名供后续使用或确认
            else:
                print(f"错误：手动提供的截图文件不存在: {use_manual_file}")
                return None
        else:
            print("准备实时截图，请确保目标窗口在前台且内容已加载。等待0.5秒...")
            time.sleep(0.5) 
            screenshot = pyautogui.screenshot()
            # 将实时截图始终保存，以便调试或后续模板匹配 (如果需要基于特定截图)
            saved_filename = f"realtime__{filename}"
            screenshot.save(saved_filename)
            print(f"实时截图已保存为 {saved_filename}")
            if for_ai_analysis:
                with open(saved_filename, "rb") as image_file:
                    encoded_string = base64.b64encode(image_file.read()).decode('utf-8')
                # os.remove(saved_filename) # 调试时可保留
                return encoded_string
            else:
                return saved_filename # 返回保存的文件名
    except Exception as e:
        print(f"处理图像时出错: {e}")
        return None

def analyze_image_with_gpt4o(base64_image, prompt_text):
    """
    使用 GPT-4o Vision API 分析图像。

    Args:
        base64_image (str): Base64 编码的图像字符串。
        prompt_text (str): 给模型的提示文本。

    Returns:
        str: 模型的文本响应。
    """
    if not base64_image:
        return "无法分析图像，因为截图未成功生成。"
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {OPENAI_API_KEY}"
    }

    payload = {
        "model": "gpt-4o",
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": prompt_text
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/png;base64,{base64_image}"
                        }
                    }
                ]
            }
        ],
        "max_tokens": 350 # 稍微增加token，以便获取更详细描述和坐标
    }

    try:
        response = client.chat.completions.create(
            model=payload["model"],
            messages=payload["messages"],
            max_tokens=payload["max_tokens"]
        )
        return response.choices[0].message.content
    except Exception as e:
        print(f"调用 OpenAI API 时出错: {e}")
        return f"调用 OpenAI API 时出错: {e}"

def extract_coordinates(text):
    """
    从文本中提取 (x, y) 格式的坐标。
    例如："相机图标大约在坐标 (123, 456)。" -> (123, 456)
    Args:
        text (str): 包含坐标信息的文本。
    Returns:
        tuple: (x, y) 坐标，如果找到的话；否则返回 None。
    """
    # 正则表达式查找括号中的两个数字，用逗号分隔，允许空格
    match = re.search(r"\(\s*(\d+)\s*,\s*(\d+)\s*\)", text)
    if match:
        x = int(match.group(1))
        y = int(match.group(2))
        return (x, y)
    return None

if __name__ == "__main__":
    # --- 自动打开浏览器并导航 --- 
    google_images_url = "https://images.google.com/"
    print(f"正在尝试自动打开浏览器并导航到: {google_images_url}")
    webbrowser.open_new_tab(google_images_url)
    print("已发送打开网页的指令。请等待页面加载（约10-12秒）。")
    print("重要提示：请在页面加载后，手动确保浏览器窗口是活动且最大化的，以便后续的图像识别能准确工作。")
    time.sleep(12) # 增加等待时间以确保页面加载和用户有机会调整窗口

    # --- 步骤 1: 使用图像模板定位并点击相机图标 --- 
    print("\n--- 步骤 1: 使用图像模板定位并点击相机图标 --- ")
    if not os.path.exists(CAMERA_ICON_TEMPLATE_PATH):
        print(f"错误：相机图标模板 '{CAMERA_ICON_TEMPLATE_PATH}' 未找到！")
        exit()

    camera_clicked_successfully = False
    try:
        print(f"正在屏幕上查找相机图标模板: '{CAMERA_ICON_TEMPLATE_PATH}'...")
        confidence_level_camera = 0.8 
        camera_coords = pyautogui.locateCenterOnScreen(CAMERA_ICON_TEMPLATE_PATH, confidence=confidence_level_camera)
        
        if camera_coords:
            print(f"通过模板成功定位到相机图标坐标: {camera_coords}")
            print(f"准备将鼠标移动到坐标 {camera_coords} 并点击 (2秒后执行)")
            time.sleep(2)
            pyautogui.moveTo(camera_coords[0], camera_coords[1], duration=0.5) # 快速移动
            pyautogui.click(camera_coords[0], camera_coords[1])
            print("已点击相机图标。")
            camera_clicked_successfully = True
            print("等待'上传文件'对话框加载...")
            time.sleep(3)
        else:
            print(f"未能通过模板 '{CAMERA_ICON_TEMPLATE_PATH}' 找到相机图标 (confidence={confidence_level_camera})。")
            # ... (fallback AI analysis can be kept or simplified) ...

    except pyautogui.ImageNotFoundException:
        print(f"PyAutoGUI错误：屏幕上找不到相机图标模板 '{CAMERA_ICON_TEMPLATE_PATH}'。")
    except Exception as e:
        print(f"在相机图标模板匹配或点击过程中发生错误: {e}")

    upload_button_clicked_successfully = False
    if camera_clicked_successfully:
        print("\n--- 步骤 2: 定位并点击上传按钮 --- ")
        if not os.path.exists(UPLOAD_BUTTON_TEMPLATE_PATH):
            print(f"错误：上传按钮模板 '{UPLOAD_BUTTON_TEMPLATE_PATH}' 未找到！")
            print(f"请先创建 '{UPLOAD_BUTTON_TEMPLATE_PATH}' 文件后再试。")
        else:
            try:
                print(f"正在屏幕上查找上传按钮模板: '{UPLOAD_BUTTON_TEMPLATE_PATH}'...")
                print("请确保'上传文件'对话框/区域在屏幕上清晰可见（等待3秒）。")
                time.sleep(3)
                confidence_level_upload = 0.8 
                upload_coords = pyautogui.locateCenterOnScreen(UPLOAD_BUTTON_TEMPLATE_PATH, confidence=confidence_level_upload)
                
                if upload_coords:
                    print(f"通过模板成功定位到上传按钮坐标: {upload_coords}")
                    pyautogui.moveTo(upload_coords[0], upload_coords[1], duration=0.5)
                    print("已移动到上传按钮，准备点击 (2秒后执行)。")
                    time.sleep(2)
                    pyautogui.click(upload_coords[0], upload_coords[1])
                    print("已点击上传按钮。")
                    upload_button_clicked_successfully = True
                    print("等待文件选择对话框出现并获取焦点...")
                    time.sleep(2) # 重要：给文件对话框足够时间出现和获得焦点
                else:
                    print(f"未能通过模板 '{UPLOAD_BUTTON_TEMPLATE_PATH}' 找到上传按钮 (confidence={confidence_level_upload})。")
                    print("请检查模板图片是否准确，以及上传对话框是否在屏幕上清晰可见。")
            except pyautogui.ImageNotFoundException:
                print(f"PyAutoGUI错误：屏幕上找不到上传按钮模板 '{UPLOAD_BUTTON_TEMPLATE_PATH}'。")
            except Exception as e:
                print(f"在上传按钮模板匹配或点击过程中发生错误: {e}")
    else:
        print("前序步骤未能成功点击相机图标，脚本终止。")

    if upload_button_clicked_successfully:
        print("\n--- 步骤 3: 处理文件上传（选择文件） --- ")
        
        # 获取要上传图片的绝对路径，以提高可靠性
        try:
            image_to_upload_abs_path = os.path.abspath(YOUR_IMAGE_TO_UPLOAD_PATH)
            print(f"将要上传的图片绝对路径: {image_to_upload_abs_path}")

            if not os.path.exists(image_to_upload_abs_path):
                print(f"错误：要上传的图片 '{image_to_upload_abs_path}' 不存在！请检查路径和文件名。")
            else:
                print(f"准备输入文件路径: '{image_to_upload_abs_path}' (3秒后执行)")
                print("请不要操作鼠标和键盘，确保文件选择对话框是当前活动窗口。")
                time.sleep(3)
                
                pyautogui.write(image_to_upload_abs_path, interval=0.05) # interval模拟人工输入速度，增加稳定性
                print("文件路径已输入。")
                time.sleep(1) # 输入后稍作停顿
                
                print("准备按 Enter 键确认文件选择 (1秒后执行)。")
                time.sleep(1)
                pyautogui.press('enter')
                print("已模拟按 Enter 键。")
                
                print("等待图片上传和页面跳转 (约10秒)... 请观察浏览器。")
                # 这里的等待时间可能需要根据网络情况和图片大小调整
                # 后续我们需要一种更可靠的方式来判断页面是否加载完毕，比如查找结果页的特定模板
                time.sleep(10) 
                print("--- 步骤 4: 分析搜索结果页面 (占位符) --- ")
                print("下一步将是捕获搜索结果页面截图，并使用新模板或AI分析来提取源URL。")

        except Exception as e:
            print(f"在处理文件上传步骤中发生错误: {e}")
            
    else:
        if camera_clicked_successfully: # 只有在相机点击成功但上传按钮失败时才显示此消息
             print("未能成功点击上传按钮，无法继续文件上传步骤。")   

    print("\n脚本主要流程执行完毕。")


    print("\n脚本执行完毕 (目前仅移动鼠标，未实际点击)。")
    # print("重要提示：pyautogui 有一个安全特性，快速将鼠标移动到屏幕任一角落可以强制停止脚本运行。") 