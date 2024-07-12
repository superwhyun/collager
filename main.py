import os
import sys
import json
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont, ExifTags
from PyQt5.QtWidgets import (QApplication, QWidget, QPushButton, QVBoxLayout, QHBoxLayout, 
                             QLabel, QFileDialog, QProgressBar, QMessageBox, QComboBox, QCheckBox, QLineEdit)
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtGui import QColor, QIcon
from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut

# 배경색 정의
BACKGROUND_COLORS = {
    "검은색": "#000000",
    "짙은 회색": "#333333",
    "연한 회색": "#CCCCCC"
}

def get_exif_rotation(img):
    try:
        for orientation in ExifTags.TAGS.keys():
            if ExifTags.TAGS[orientation] == 'Orientation':
                break
        exif = dict(img._getexif().items())
        if exif[orientation] == 2:
            return img.transpose(Image.FLIP_LEFT_RIGHT)
        elif exif[orientation] == 3:
            return img.transpose(Image.ROTATE_180)
        elif exif[orientation] == 4:
            return img.transpose(Image.FLIP_TOP_BOTTOM)
        elif exif[orientation] == 5:
            return img.transpose(Image.ROTATE_90).transpose(Image.FLIP_TOP_BOTTOM)
        elif exif[orientation] == 6:
            return img.transpose(Image.ROTATE_270)
        elif exif[orientation] == 7:
            return img.transpose(Image.ROTATE_270).transpose(Image.FLIP_TOP_BOTTOM)
        elif exif[orientation] == 8:
            return img.transpose(Image.ROTATE_90)
    except (AttributeError, KeyError, IndexError, TypeError):
        pass
    return img

def get_exif_data(image, image_path):
    exif_data = {}
    try:
        if hasattr(image, '_getexif'):  # JPEG 파일인 경우
            info = image._getexif()
            if info:
                for tag_id, value in info.items():
                    tag = ExifTags.TAGS.get(tag_id, tag_id)
                    if tag == "GPSInfo":
                        gps_data = {}
                        for t in value:
                            sub_tag = ExifTags.GPSTAGS.get(t, t)
                            gps_data[sub_tag] = value[t]
                        exif_data[tag] = gps_data
                    else:
                        exif_data[tag] = value
        else:  # PNG 등 EXIF 데이터가 없는 파일의 경우
            exif_data['DateTime'] = datetime.fromtimestamp(os.path.getmtime(image_path)).strftime('%Y:%m:%d %H:%M:%S')
    except Exception as e:
        print(f"Error getting EXIF data: {str(e)}")
    return exif_data

def get_decimal_coordinates(info):
    try:
        for key in ['Latitude', 'Longitude']:
            if 'GPS'+key in info and 'GPS'+key+'Ref' in info:
                e = info['GPS'+key]
                ref = info['GPS'+key+'Ref']
                info[key] = ( convert_to_degrees(e[0]) +
                              convert_to_degrees(e[1]) / 60 +
                              convert_to_degrees(e[2]) / 3600
                            ) * (-1 if ref in ['S','W'] else 1)
        if 'Latitude' in info and 'Longitude' in info:
            return [info['Latitude'], info['Longitude']]
    except Exception as e:
        print(f"Error getting decimal coordinates: {str(e)}")
    return None

def convert_to_degrees(value):
    if isinstance(value, tuple):
        return float(value[0]) / float(value[1])
    return float(value)

def get_address(gps_coords):
    if gps_coords is None:
        return ""  # 위치 정보가 없을 경우 빈 문자열 반환
    geolocator = Nominatim(user_agent="my_agent")
    try:
        location = geolocator.reverse(f"{gps_coords[0]}, {gps_coords[1]}")
        if location:
            address = location.raw['address']
            province = address.get('province', '')
            city = address.get('city', '')
            town = address.get('town', '')
            
            if city or town:
                if province:
                    return f"{province} {city}".strip()
                else:    
                    return f"{city} {town}".strip()
            
            village = address.get('village', '')
            suburb = address.get('suburb', '')
            
            if village or suburb:
                return f"{village} {suburb}".strip()
        
        return ""  # 주소 정보를 찾지 못한 경우 빈 문자열 반환
    except GeocoderTimedOut:
        return ""
    except Exception as e:
        print(f"Error getting address: {str(e)}")
        return ""

def apply_timestamp(img, exif_data, font_path):
    img_width, img_height = img.size
    base_font_size = int(min(img_width, img_height) * 0.04)
    
    time_font = ImageFont.truetype(font_path, base_font_size * 2)
    date_font = ImageFont.truetype(font_path, int(base_font_size * 0.8))
    weekday_font = ImageFont.truetype(font_path, int(base_font_size * 0.7))
    address_font = ImageFont.truetype(font_path, int(base_font_size * 0.7))

    date_taken = exif_data.get('DateTime', exif_data.get('DateTimeOriginal', datetime.now().strftime('%Y:%m:%d %H:%M:%S')))
    try:
        date_obj = datetime.strptime(date_taken, '%Y:%m:%d %H:%M:%S')
    except ValueError:
        date_obj = datetime.now()
    
    weekdays = ['월요일', '화요일', '수요일', '목요일', '금요일', '토요일', '일요일']
    weekday = weekdays[date_obj.weekday()]
    
    gps_info = exif_data.get('GPSInfo', {})
    gps_coords = get_decimal_coordinates(gps_info)
    address = get_address(gps_coords)

    draw = ImageDraw.Draw(img)
    
    time_text = f"{date_obj.strftime('%H:%M')}"
    date_text = f"{date_obj.strftime('%Y/%m/%d')}"
    weekday_text = f"{weekday}"
    
    margin = int(min(img_width, img_height) * 0.03)
    line_spacing = int(base_font_size * 0.5)
    
    # 시간 텍스트 위치 계산
    time_bbox = draw.textbbox((0, 0), time_text, font=time_font)
    time_width = time_bbox[2] - time_bbox[0]
    time_height = time_bbox[3] - time_bbox[1]
    time_x = margin
    time_y = img_height - time_height - margin * 2 - (address_font.size if address else 0) - line_spacing

    # 날짜 텍스트 위치 계산
    date_x = time_x + time_width + margin // 2 + int(time_height * 0.1) + margin // 2
    date_y = time_y
    
    # 요일 텍스트 위치 계산
    weekday_x = date_x
    weekday_y = date_y + date_font.size + line_spacing // 2
    
    # 노란색 바 추가 (길이를 절반으로 조정)
    bar_width = int(time_height * 0.1)
    bar_x = time_x + time_width + margin // 2
    bar_y = time_y  # 바의 시작 위치를 약간 아래로 조정
    bar_height = (time_height + date_font.size + weekday_font.size + line_spacing) // 2  # 길이를 절반으로 줄임
    draw.rectangle([bar_x, bar_y, bar_x + bar_width, bar_y + bar_height], fill=(255, 255, 0))
    
    # 주소 텍스트 위치 계산
    address_y = time_y + time_height + line_spacing
    
    # 텍스트 그리기
    draw.text((time_x, time_y), time_text, font=time_font, fill=(255, 255, 255))
    draw.text((date_x, date_y), date_text, font=date_font, fill=(255, 255, 255))
    draw.text((weekday_x, weekday_y), weekday_text, font=weekday_font, fill=(255, 255, 255))
    if address:
        draw.text((margin, address_y), address, font=address_font, fill=(255, 255, 255))

    return img

def create_collage(image_files, output_path, background_color, should_add_timestamp, font_path):
    A4_WIDTH, A4_HEIGHT = 3508, 2480
    MARGIN_TOP_BOTTOM = int(0.3 * 300)
    MARGIN_LEFT_RIGHT = int(0.5 * 300)
    MARGIN_BETWEEN_ROWS = int(0.1 * 300)
    MARGIN_BETWEEN_IMAGES = int(0.02 * 300)
    IMAGE_MARGIN = int(0.02 * 300)
    CONTENT_WIDTH = A4_WIDTH - (2 * MARGIN_LEFT_RIGHT)
    CONTENT_HEIGHT = A4_HEIGHT - (2 * MARGIN_TOP_BOTTOM) - MARGIN_BETWEEN_ROWS
    row_height = (CONTENT_HEIGHT - MARGIN_BETWEEN_ROWS) // 2

    bg_color = tuple(int(background_color.lstrip('#')[i:i+2], 16) for i in (0, 2, 4))
    collage = Image.new('RGB', (A4_WIDTH, A4_HEIGHT), bg_color)
    draw = ImageDraw.Draw(collage)
    
    def fit_image(img, target_width, target_height):
        img_ratio = img.width / img.height
        target_ratio = target_width / target_height

        if img_ratio > target_ratio:
            # 이미지가 더 넓은 경우
            new_width = target_width
            new_height = int(new_width / img_ratio)
        else:
            # 이미지가 더 높은 경우
            new_height = target_height
            new_width = int(new_height * img_ratio)

        img_resized = img.resize((new_width, new_height), Image.LANCZOS)
        
        # 배경 이미지 생성 및 리사이즈된 이미지 중앙에 배치
        background = Image.new('RGB', (target_width, target_height), bg_color)
        offset = ((target_width - new_width) // 2, (target_height - new_height) // 2)
        background.paste(img_resized, offset)
        
        return background

    def is_portrait(img_path):
        with Image.open(img_path) as img:
            return img.height > img.width

    def place_images_in_row(row_image_files, y_offset):
        is_all_portrait = all(is_portrait(img) for img in row_image_files[:4])
        
        max_images = 4 if is_all_portrait else 3
        x_offset = MARGIN_LEFT_RIGHT
        used_images = 0
        row_width = 0
        
        if is_all_portrait:
            target_width = (CONTENT_WIDTH - (3 * MARGIN_BETWEEN_IMAGES)) // 4
            target_height = row_height - (2 * IMAGE_MARGIN)
        else:
            target_height = row_height - (2 * IMAGE_MARGIN)
            target_width = (CONTENT_WIDTH - (2 * MARGIN_BETWEEN_IMAGES)) // 3
        
        fitted_images = []
        for img_path in row_image_files[:max_images]:
            with Image.open(img_path) as img:
                img = get_exif_rotation(img)
                if should_add_timestamp:
                    exif_data = get_exif_data(img, img_path)
                    img = apply_timestamp(img, exif_data, font_path)
                fitted_images.append(fit_image(img, target_width, target_height))
        
        placed_images = []
        for img in fitted_images:
            img_with_margin = Image.new('RGB', (img.width + 2*IMAGE_MARGIN, img.height + 2*IMAGE_MARGIN), bg_color)
            img_with_margin.paste(img, (IMAGE_MARGIN, IMAGE_MARGIN))
            
            collage.paste(img_with_margin, (x_offset, y_offset))
            placed_images.append((x_offset, y_offset, x_offset + img_with_margin.width, y_offset + img_with_margin.height))
            x_offset += img_with_margin.width + MARGIN_BETWEEN_IMAGES
            row_width = x_offset - MARGIN_LEFT_RIGHT - MARGIN_BETWEEN_IMAGES
            used_images += 1

        return used_images, row_width, placed_images

    used_images = 0
    used_images_row1, row1_width, placed_images_row1 = place_images_in_row(image_files, MARGIN_TOP_BOTTOM)
    used_images += used_images_row1

    used_images_row2, row2_width, placed_images_row2 = place_images_in_row(image_files[used_images:], MARGIN_TOP_BOTTOM + row_height + MARGIN_BETWEEN_ROWS)
    used_images += used_images_row2

    max_row_width = max(row1_width, row2_width)
    gray_color = (200, 200, 200)

    def draw_safe_rectangle(coordinates):
        x1, y1, x2, y2 = coordinates
        if x2 > x1 and y2 > y1:
            draw.rectangle([x1, y1, x2, y2], fill=gray_color)

    if placed_images_row1:
        last_image_row1 = placed_images_row1[-1]
        if row1_width < max_row_width:
            gray_width = max_row_width - row1_width
            draw_safe_rectangle([
                last_image_row1[2] + MARGIN_BETWEEN_IMAGES + 2,
                last_image_row1[1] + 1,
                last_image_row1[2] + MARGIN_BETWEEN_IMAGES - 2 + gray_width,
                last_image_row1[3] - 2
            ])

    if placed_images_row2:
        last_image_row2 = placed_images_row2[-1]
        if row2_width < max_row_width:
            gray_width = max_row_width - row2_width
            draw_safe_rectangle([
                last_image_row2[2] + MARGIN_BETWEEN_IMAGES + 2,
                last_image_row2[1],
                last_image_row2[2] + MARGIN_BETWEEN_IMAGES - 2 + gray_width,
                last_image_row2[3] - 2
            ])

    collage.save(output_path, 'PDF', resolution=300.0, quality=95)
    return used_images

def process_images(input_folder, output_folder, background_color, add_timestamp, font_path):
    image_files = [os.path.join(input_folder, f) for f in os.listdir(input_folder) 
                   if f.lower().endswith(('.png', '.jpg', '.jpeg'))]
    image_files.sort(key=lambda x: os.path.getmtime(x))

    total_images = len(image_files)
    collage_count = 1
    processed_images = 0

    while image_files:
        output_file = os.path.join(output_folder, f"collage_{collage_count}.pdf")
        num_used_images = create_collage(image_files, output_file, background_color, add_timestamp, font_path)
        
        processed_images += num_used_images
        yield int(processed_images / total_images * 100)
        
        collage_count += 1
        image_files = image_files[num_used_images:]

class CollageThread(QThread):
    progress = pyqtSignal(int)
    finished = pyqtSignal()

    def __init__(self, input_folder, output_folder, background_color, add_timestamp, font_path):
        super().__init__()
        self.input_folder = input_folder
        self.output_folder = output_folder
        self.background_color = background_color
        self.add_timestamp = add_timestamp
        self.font_path = font_path

    def run(self):
        for progress in process_images(self.input_folder, self.output_folder, self.background_color, self.add_timestamp, self.font_path):
            self.progress.emit(progress)
        self.finished.emit()

class CollageApp(QWidget):
    def __init__(self):
        super().__init__()
        self.settings_file = "collage_settings.json"
        self.load_settings()
        self.initUI()

    def initUI(self):
        self.setWindowTitle('콜라주 생성기')
        self.setGeometry(300, 300, 500, 300)
        
        # 아이콘 설정
        icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icon.ico")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))
        else:
            print(f"아이콘 파일을 찾을 수 없습니다: {icon_path}")

        layout = QVBoxLayout()

        # 입력 폴더 선택
        input_layout = QHBoxLayout()
        self.input_edit = QLineEdit(self.settings.get("input_folder", ""))
        input_button = QPushButton('입력 폴더 선택')
        input_button.clicked.connect(self.select_input_folder)
        input_layout.addWidget(self.input_edit)
        input_layout.addWidget(input_button)
        layout.addLayout(input_layout)

        # 출력 폴더 선택
        output_layout = QHBoxLayout()
        self.output_edit = QLineEdit(self.settings.get("output_folder", ""))
        output_button = QPushButton('출력 폴더 선택')
        output_button.clicked.connect(self.select_output_folder)
        output_layout.addWidget(self.output_edit)
        output_layout.addWidget(output_button)
        layout.addLayout(output_layout)

        # 배경색 선택
        color_layout = QHBoxLayout()
        color_label = QLabel('배경색:')
        self.color_combo = QComboBox()
        self.color_combo.addItems(BACKGROUND_COLORS.keys())
        self.color_combo.setCurrentText(self.settings.get("background_color", "검은색"))
        self.color_combo.currentTextChanged.connect(self.update_background_color)
        color_layout.addWidget(color_label)
        color_layout.addWidget(self.color_combo)
        layout.addLayout(color_layout)

        # 타임스탬프 체크박스
        self.timestamp_checkbox = QCheckBox('타임스탬프 추가')
        self.timestamp_checkbox.setChecked(self.settings.get("add_timestamp", False))
        layout.addWidget(self.timestamp_checkbox)

        # 폰트 선택
        font_layout = QHBoxLayout()
        font_label = QLabel('폰트:')
        self.font_combo = QComboBox()
        self.load_fonts()
        font_layout.addWidget(font_label)
        font_layout.addWidget(self.font_combo)
        layout.addLayout(font_layout)

        # 처리 시작 버튼
        self.generate_button = QPushButton('콜라주 생성')
        self.generate_button.clicked.connect(self.generate_collages)
        layout.addWidget(self.generate_button)

        # 진행 상황 표시 바
        self.progress_bar = QProgressBar()
        layout.addWidget(self.progress_bar)

        self.setLayout(layout)

    def load_fonts(self):
        script_dir = os.path.dirname(os.path.abspath(__file__))
        font_dir = os.path.join(script_dir, "fonts")
        
        if os.path.exists(font_dir):
            font_files = [f for f in os.listdir(font_dir) if f.lower().endswith(('.ttf', '.otf', '.ttc'))]
            self.font_combo.addItems(font_files)
            self.font_combo.setCurrentText(self.settings.get("font", font_files[0] if font_files else ""))
        else:
            print(f"{font_dir} 폴더를 찾을 수 없습니다.")

    def load_settings(self):
        try:
            with open(self.settings_file, "r") as f:
                self.settings = json.load(f)
        except FileNotFoundError:
            self.settings = {}

    def save_settings(self):
        self.settings["input_folder"] = self.input_edit.text()
        self.settings["output_folder"] = self.output_edit.text()
        self.settings["background_color"] = self.color_combo.currentText()
        self.settings["add_timestamp"] = self.timestamp_checkbox.isChecked()
        self.settings["font"] = self.font_combo.currentText()
        
        with open(self.settings_file, "w") as f:
            json.dump(self.settings, f)

    def select_input_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "입력 폴더 선택", self.input_edit.text())
        if folder:
            self.input_edit.setText(folder)

    def select_output_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "출력 폴더 선택", self.output_edit.text())
        if folder:
            self.output_edit.setText(folder)

    def update_background_color(self, color_name):
        self.background_color = BACKGROUND_COLORS[color_name]

    def generate_collages(self):
        input_folder = self.input_edit.text()
        output_folder = self.output_edit.text()
        
        if not input_folder or not output_folder:
            QMessageBox.warning(self, "오류", "입력 및 출력 폴더를 모두 선택해주세요.")
            return

        self.save_settings()

        background_color = BACKGROUND_COLORS[self.color_combo.currentText()]
        add_timestamp = self.timestamp_checkbox.isChecked()
        font_filename = self.font_combo.currentText()
        font_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fonts", font_filename)

        self.generate_button.setEnabled(False)
        self.progress_bar.setValue(0)

        self.thread = CollageThread(input_folder, output_folder, background_color, add_timestamp, font_path)
        self.thread.progress.connect(self.update_progress)
        self.thread.finished.connect(self.on_finished)
        self.thread.start()

    def update_progress(self, value):
        self.progress_bar.setValue(value)

    def on_finished(self):
        self.generate_button.setEnabled(True)
        QMessageBox.information(self, "완료", "모든 콜라주 생성이 완료되었습니다.")

if __name__ == '__main__':
    app = QApplication(sys.argv)
    ex = CollageApp()
    ex.show()
    sys.exit(app.exec_())