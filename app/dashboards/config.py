"""
Centralized configuration for dashboards
"""
import os
from pathlib import Path
import json
from typing import Dict, Any

class DashboardConfig:
    """Centralized configuration for dashboards"""
    
    BASE_DIR = Path(__file__).parent.parent
    
    # Database paths
    FACULTY_DB = os.getenv(
        "FACULTY_DB_PATH",
        str(BASE_DIR / "fetch_data" / "faculty_data.db")
    )
    ACCESS_CONTROL_DB = os.getenv(
        "ACCESS_CONTROL_DB_PATH",
        str(BASE_DIR / "access_control.db")
    )
    
    # Service URLs
    METRICS_SERVICE_URL = os.getenv(
        "METRICS_SERVICE_URL",
        "http://127.0.0.1:6000/metrics"
    )
    
    # Cache settings
    CACHE_ENABLED = os.getenv("DASHBOARD_CACHE_ENABLED", "true").lower() == "true"
    CACHE_TTL = int(os.getenv("DASHBOARD_CACHE_TTL", "300"))
    
    # Shapefile path
    IRAN_SHAPEFILE = BASE_DIR / "data" / "iran_shapefile" / "gadm41_IRN_1.shp"
    
    # Province mappings
    _province_mappings = None
    
    # Zone mappings for LMS
    ZONES = {
        "Zone1": "تهران، شهرستانهای تهران و البرز",
        "Zone2": "گیلان، مازندران و گلستان",
        "Zone3": "آذربایجان شرقی، آذربایجان غربی، اردبیل و زنجان",
        "Zone4": "قم، قزوین، مرکزی و همدان",
        "Zone5": "ایلام، کردستان، کرمانشاه و لرستان",
        "Zone6": "اصفهان، چهارمحال و بختیاری و یزد",
        "Zone7": "کهگیلویه و بویراحمد و فارس",
        "Zone8": "سیستان و بلوچستان، کرمان، هرمزگان",
        "Zone9": "خراسان رضوی، جنوبی و شمالی و سمنان",
        "Zone10": "بوشهر و خوزستان",
        "Zone11": "سامانه جلسات"
    }
    
    HOSTNAMES = {
        "Zone1": "lms1",
        "Zone2": "lms2",
        "Zone3": "lms3",
        "Zone4": "lms4",
        "Zone5": "lms5",
        "Zone6": "lms6",
        "Zone7": "lms7",
        "Zone8": "lms8",
        "Zone9": "lms9",
        "Zone10": "lms10",
        "Zone11": "meeting"
    }
    
    @classmethod
    def get_province_mappings(cls) -> Dict[str, str]:
        """Load province mappings from JSON file"""
        if cls._province_mappings is None:
            mapping_file = cls.BASE_DIR / "data" / "province_mappings.json"
            if mapping_file.exists():
                try:
                    with open(mapping_file, 'r', encoding='utf-8') as f:
                        cls._province_mappings = json.load(f)
                except Exception as e:
                    print(f"Error loading province mappings: {e}")
                    cls._province_mappings = cls._get_default_mappings()
            else:
                cls._province_mappings = cls._get_default_mappings()
        return cls._province_mappings.get('persian_to_english', {})
    
    @classmethod
    def _get_default_mappings(cls) -> Dict[str, Any]:
        """Default province mappings"""
        return {
            "persian_to_english": {
                "آذربایجان شرقی": "east azarbaijan",
                "آذربایجان غربی": "west azarbaijan",
                "اردبیل": "ardebil",
                "اصفهان": "esfahan",
                "البرز": "alborz",
                "ایلام": "ilam",
                "بوشهر": "bushehr",
                "تهران": "tehran",
                "چهارمحال بختیاری": "chahar mahall and bakhtiari",
                "خراسان جنوبی": "south khorasan",
                "خراسان رضوی": "razavi khorasan",
                "خراسان شمالی": "north khorasan",
                "خوزستان": "khuzestan",
                "زنجان": "zanjan",
                "سمنان": "semnan",
                "سیستان و بلوچستان": "sistan and baluchestan",
                "فارس": "fars",
                "قزوین": "qazvin",
                "قم": "qom",
                "کردستان": "kordestan",
                "کرمان": "kerman",
                "کرمانشاه": "kermanshah",
                "کهگیلویه و بویراحمد": "kohgiluyeh and buyer ahmad",
                "گلستان": "golestan",
                "گیلان": "gilan",
                "لرستان": "lorestan",
                "مازندران": "mazandaran",
                "مرکزی": "markazi",
                "هرمزگان": "hormozgan",
                "همدان": "hamadan",
                "یزد": "yazd"
            }
        }


