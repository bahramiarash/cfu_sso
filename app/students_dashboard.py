# backend route for students_dashboard.html
from flask import Blueprint, render_template
import collections
import json
import logging
from models import get_db_connection, get_db_connection2
import locale
import functools

# تنظیم locale برای فارسی (در لینوکس/یونیکس باید locale نصب باشد)
try:
    locale.setlocale(locale.LC_COLLATE, 'fa_IR.UTF-8')
except locale.Error:
    # اگر روی سرور locale فارسی نصب نیست، از روش سفارشی استفاده می‌کنیم
    locale.setlocale(locale.LC_COLLATE, 'C')
persian_order = 'اآبپتثجچحخدذرزژسشصضطظعغفقکگلمنوهی'
def persian_sort_key(word):
    word = word.strip()
    return [persian_order.index(ch) if ch in persian_order else ord(ch) for ch in word]

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

students_bp = Blueprint('students_dashboard', __name__)

@students_bp.route('/dashboards/students')
def students_dashboard():
    conn = get_db_connection2()
    cursor = conn.cursor()

    # Grouped student data for the summary table
    cursor.execute('''
        SELECT sub_uniname, gradname, course_name,
               COUNT(*) as total,
               SUM(CASE WHEN sex LIKE '%آقا%' THEN 1 ELSE 0 END) as male,
               SUM(CASE WHEN sex LIKE '%خانم%' THEN 1 ELSE 0 END) as female
        FROM Students
        GROUP BY sub_uniname, gradname, course_name
        ORDER BY sub_uniname, gradname, course_name
    ''')
    grouped_rows = cursor.fetchall()

    grouped_data = [
        {
            'sub_uniname': row['sub_uniname'],
            'gradname': row['gradname'],
            'course_name': row['course_name'],
            'total': row['total'],
            'male': row['male'],
            'female': row['female']
        }
        for row in grouped_rows
    ]

    # Gender chart data
    cursor.execute('''
        SELECT sex, COUNT(*) as count FROM Students GROUP BY sex
    ''')
    gender_rows = cursor.fetchall()
    gender_data = {
        "labels": [row['sex'].strip() for row in gender_rows],
        "counts": [row['count'] for row in gender_rows]
    }
    # === Get 'vazeiyat' distribution ===
    cursor.execute("""
        SELECT vazeiyat, COUNT(*) 
        FROM students 
        GROUP BY vazeiyat
        ORDER BY COUNT(*) DESC
    """)
    vazeiyat_rows = cursor.fetchall()

    vazeiyat_data = {
        "labels": [row[0] if row[0] else "نامشخص" for row in vazeiyat_rows],
        "counts": [row[1] for row in vazeiyat_rows]
    }

    # === Get 'vazeiyat' distribution 1404 ===
    cursor.execute("""
        SELECT vazeiyat, COUNT(*) 
        FROM students 
        WHERE SUBSTR(studentnum, 1, 3) = '404'
        GROUP BY vazeiyat
        ORDER BY COUNT(*) DESC
    """)
    vazeiyat_rows_404 = cursor.fetchall()

    vazeiyat_data_404 = {
        "labels": [row[0] if row[0] else "نامشخص" for row in vazeiyat_rows_404],
        "counts": [row[1] for row in vazeiyat_rows_404]
    }
    # === Get 'vazeiyat' distribution 1404 province ===
    # === Province + Vazeiyat Distribution ===
    cursor.execute("""
        SELECT trim(province), vazeiyat, COUNT(*)
        FROM students
        GROUP BY province, vazeiyat
        ORDER BY trim(province)
    """)
    rows = cursor.fetchall()
    rows.sort(key=lambda x: locale.strxfrm(x[0] or ""))

    # Convert to structure suitable for Chart.js
    from collections import defaultdict

    province_vazeiyat = defaultdict(lambda: defaultdict(int))
    for province, vazeiyat, count in rows:
        province_vazeiyat[province][vazeiyat or "نامشخص"] = count
    sorted_provinces = sorted(province_vazeiyat.keys(), key=persian_sort_key)
    vazeiyat_categories = sorted({v for p in province_vazeiyat.values() for v in p.keys()})
    datasets = []
    import random
    for vazeiyat in vazeiyat_categories:
        datasets.append({
            "label": vazeiyat,
            "data": [province_vazeiyat[prov].get(vazeiyat, 0) for prov in sorted_provinces],
            "backgroundColor": f"rgba({random.randint(50,200)}, {random.randint(80,200)}, {random.randint(150,255)}, 0.8)"
        })
    # Extract labels and datasets

    province_vazeiyat_data = {
        "labels": sorted_provinces,
        "datasets": datasets
    }


    # Gender chart data
    cursor.execute('''
        SELECT sex, COUNT(*) as count FROM Students WHERE SUBSTR(studentnum, 1, 3) = '404' GROUP BY sex
    ''')
    gender_rows_404 = cursor.fetchall()
    gender_data_404 = {
        "labels": [row['sex'].strip() for row in gender_rows_404],
        "counts": [row['count'] for row in gender_rows_404]
    }

    # Course chart data
    cursor.execute('''
        SELECT course_name, COUNT(*) as count FROM Students GROUP BY course_name ORDER BY count DESC
    ''')
    course_rows = cursor.fetchall()
    course_data = {
        "labels": [row['course_name'] for row in course_rows],
        "counts": [row['count'] for row in course_rows]
    }
    # Course chart data
    cursor.execute('''
        SELECT course_name, COUNT(*) as count FROM Students WHERE grade=1 GROUP BY course_name ORDER BY count DESC
    ''')
    course_rows = cursor.fetchall()
    course_data_kardani = {
        "labels": [row['course_name'] for row in course_rows],
        "counts": [row['count'] for row in course_rows]
    }
    # Course chart data
    cursor.execute('''
        SELECT course_name, COUNT(*) as count FROM Students WHERE grade=2 GROUP BY course_name ORDER BY count DESC
    ''')
    course_rows = cursor.fetchall()
    course_data_napeyvaste = {
        "labels": [row['course_name'] for row in course_rows],
        "counts": [row['count'] for row in course_rows]
    }

    # Course chart data
    cursor.execute('''
        SELECT course_name, COUNT(*) as count FROM Students WHERE grade=3 GROUP BY course_name ORDER BY count DESC
    ''')
    course_rows = cursor.fetchall()
    course_data_peyvaste = {
        "labels": [row['course_name'] for row in course_rows],
        "counts": [row['count'] for row in course_rows]
    }

    # Course chart data
    cursor.execute('''
        SELECT course_name, COUNT(*) as count FROM Students WHERE grade=4 GROUP BY course_name ORDER BY count DESC
    ''')
    course_rows = cursor.fetchall()
    course_data_arshad = {
        "labels": [row['course_name'] for row in course_rows],
        "counts": [row['count'] for row in course_rows]
    }

    # Grade chart data
    cursor.execute('''
        SELECT gradname, COUNT(*) as count FROM Students GROUP BY gradname
    ''')
    grade_rows = cursor.fetchall()
    grade_data = {
        "labels": [row['gradname'] for row in grade_rows],
        "counts": [row['count'] for row in grade_rows]
    }

    # Province chart data
    cursor.execute('''
        SELECT province, COUNT(*) as count FROM Students GROUP BY province  ORDER BY province
    ''')
    province_rows = cursor.fetchall()
    province_data = {
        "labels": [row['province'] for row in province_rows],
        "counts": [row['count'] for row in province_rows]
    }
    # #########################################################

    # Province Year chart data
    cursor.execute('''
        SELECT substr(term, 1, 3) AS year,
            province,
            COUNT(*) AS count
        FROM Students
        GROUP BY year, province
        ORDER BY province, year
    ''')
    province_year_rows = cursor.fetchall()

    # Extract unique province names in the order they appear
    provinces = sorted(set(row['province'] for row in province_year_rows))
    years = sorted(set(row['year'] for row in province_year_rows))

    # Prepare data dict with zeros by default
    data_by_year = {year: [0] * len(provinces) for year in years}

    # Fill the counts
    for row in province_year_rows:
        province_idx = provinces.index(row['province'])
        data_by_year[row['year']][province_idx] = row['count']

    province_year_data = {
        "labels": provinces,
        "years": years,
        "data": data_by_year
    }
    # ###############################################################
    # #########################################################

    # Province Sex chart data
    cursor.execute('''
        SELECT sex,
            province,
            COUNT(*) AS count
        FROM Students
        GROUP BY sex, province
        ORDER BY province, sex
    ''')
    province_sex_rows = cursor.fetchall()

    # Extract unique province names in the order they appear
    provinces = sorted(set(row['province'] for row in province_sex_rows))
    sex_list = sorted(set(row['sex'] for row in province_sex_rows))

    # Prepare data dict with zeros by default
    data_by_sex = {sex: [0] * len(provinces) for sex in sex_list}

    # Fill the counts
    for row in province_sex_rows:
        province_idx = provinces.index(row['province'])
        data_by_sex[row['sex']][province_idx] = row['count']

    province_sex_data = {
        "labels": provinces,
        "sex_list": sex_list,
        "data": data_by_sex
    }
    # ###############################################################

    # Entry year chart (based on studentnum)
    cursor.execute('''
        SELECT SUBSTR(studentnum, 1, 3) as prefix,
               COUNT(*) as total,
               SUM(CASE WHEN sex LIKE '%آقا%' THEN 1 ELSE 0 END) as male,
               SUM(CASE WHEN sex LIKE '%خانم%' THEN 1 ELSE 0 END) as female
        FROM Students
        GROUP BY prefix
        ORDER BY prefix
    ''')
    year_rows = cursor.fetchall()
    year_data = {
        "labels": [str(1400 + int(row['prefix']) - 400) for row in year_rows],
        "total": [row['total'] for row in year_rows],
        "male": [row['male'] for row in year_rows],
        "female": [row['female'] for row in year_rows]
    }

    # Entry year chart (based on studentnum)
    cursor.execute('''
        SELECT SUBSTR(studentnum, 1, 3) as prefix,
               SUM(CASE WHEN grade = 1 THEN 1 ELSE 0 END) as kardani,
               SUM(CASE WHEN grade = 2 THEN 1 ELSE 0 END) as napeyvaste,
               SUM(CASE WHEN grade = 3 THEN 1 ELSE 0 END) as peyvaste,
               SUM(CASE WHEN grade = 4 THEN 1 ELSE 0 END) as arshad
        FROM Students
        GROUP BY prefix
        ORDER BY prefix
    ''')
    year_rows = cursor.fetchall()
    year_data_grade = {
        "labels": [str(1400 + int(row['prefix']) - 400) for row in year_rows],
        "kardani": [row['kardani'] for row in year_rows],
        "peyvaste": [row['peyvaste'] for row in year_rows],
        "napeyvaste": [row['napeyvaste'] for row in year_rows],
        "arshad": [row['arshad'] for row in year_rows],
    }

    # Entry year vs course Kardani
    cursor.execute('''
        SELECT SUBSTR(studentnum, 1, 3) as prefix, course_name, COUNT(*) as count
        FROM Students
        WHERE grade=1
        GROUP BY prefix, course_name
        ORDER BY count
    ''')
    rows = cursor.fetchall()
    course_years = {}
    all_years = set()

    for row in rows:
        year = str(1400 + int(row['prefix']) - 400)
        course = row['course_name']
        count = row['count']
        all_years.add(year)
        course_years.setdefault(course, {})[year] = count

    sorted_years = sorted(all_years)

    course_year_data_kardani = {
        "labels": sorted_years,
        "datasets": [
            {
                "label": course,
                "data": [course_years[course].get(year, 0) for year in sorted_years]
            } for course in course_years
        ]
    }

    # Entry year vs course Karshenasi Napeyvaste
    cursor.execute('''
        SELECT SUBSTR(studentnum, 1, 3) as prefix, course_name, COUNT(*) as count
        FROM Students
        WHERE grade=2
        GROUP BY prefix, course_name
        ORDER BY count
    ''')
    rows = cursor.fetchall()
    course_years = {}
    all_years = set()

    for row in rows:
        year = str(1400 + int(row['prefix']) - 400)
        course = row['course_name']
        count = row['count']
        all_years.add(year)
        course_years.setdefault(course, {})[year] = count

    sorted_years = sorted(all_years)

    course_year_data_karshenasi_napeyvaste = {
        "labels": sorted_years,
        "datasets": [
            {
                "label": course,
                "data": [course_years[course].get(year, 0) for year in sorted_years]
            } for course in course_years
        ]
    }    

    # Entry year vs course Karshenasi Peyvaste
    cursor.execute('''
        SELECT SUBSTR(studentnum, 1, 3) as prefix, course_name, COUNT(*) as count
        FROM Students
        WHERE grade=3
        GROUP BY prefix, course_name
        ORDER BY count
    ''')
    rows = cursor.fetchall()
    course_years = {}
    all_years = set()

    for row in rows:
        year = str(1400 + int(row['prefix']) - 400)
        course = row['course_name']
        count = row['count']
        all_years.add(year)
        course_years.setdefault(course, {})[year] = count

    sorted_years = sorted(all_years)

    course_year_data_karshenasi_peyvaste = {
        "labels": sorted_years,
        "datasets": [
            {
                "label": course,
                "data": [course_years[course].get(year, 0) for year in sorted_years]
            } for course in course_years
        ]
    }    

    # Entry year vs course Arshad
    cursor.execute('''
        SELECT SUBSTR(studentnum, 1, 3) as prefix, course_name, COUNT(*) as count
        FROM Students
        WHERE grade=4
        GROUP BY prefix, course_name
        ORDER BY count
    ''')
    rows = cursor.fetchall()
    course_years = {}
    all_years = set()

    for row in rows:
        year = str(1400 + int(row['prefix']) - 400)
        course = row['course_name']
        count = row['count']
        all_years.add(year)
        course_years.setdefault(course, {})[year] = count

    sorted_years = sorted(all_years)

    course_year_data_arshad = {
        "labels": sorted_years,
        "datasets": [
            {
                "label": course,
                "data": [course_years[course].get(year, 0) for year in sorted_years]
            } for course in course_years
        ]
    }    
    # Entry year vs course
    cursor.execute('''
        SELECT SUBSTR(studentnum, 1, 3) as prefix, course_name, COUNT(*) as count
        FROM Students
        WHERE grade=1
        GROUP BY prefix, course_name
        ORDER BY count
    ''')
    rows = cursor.fetchall()
    course_years = {}
    all_years = set()

    for row in rows:
        year = str(1400 + int(row['prefix']) - 400)
        course = row['course_name']
        count = row['count']
        all_years.add(year)
        course_years.setdefault(course, {})[year] = count

    sorted_years = sorted(all_years)

    course_year_data = {
        "labels": sorted_years,
        "datasets": [
            {
                "label": course,
                "data": [course_years[course].get(year, 0) for year in sorted_years]
            } for course in course_years
        ]
    }


    conn.close()

    return render_template(
        'dashboards/students_dashboard.html',
        grouped_data=grouped_data,
        gender_data=json.dumps(gender_data),
        gender_data_404=json.dumps(gender_data_404),
        course_data=json.dumps(course_data),
        course_data_kardani=json.dumps(course_data_kardani),
        course_data_napeyvaste=json.dumps(course_data_napeyvaste),
        course_data_peyvaste=json.dumps(course_data_peyvaste),
        course_data_arshad=json.dumps(course_data_arshad),
        grade_data=json.dumps(grade_data),
        province_data=json.dumps(province_data),
        province_year_data=json.dumps(province_year_data),
        province_sex_data=json.dumps(province_sex_data),
        year_data=json.dumps(year_data),
        year_data_grade=json.dumps(year_data_grade),
        course_year_data_kardani=json.dumps(course_year_data_kardani),
        course_year_data_karshenasi_napeyvaste=json.dumps(course_year_data_karshenasi_napeyvaste),
        course_year_data_karshenasi_peyvaste=json.dumps(course_year_data_karshenasi_peyvaste),
        course_year_data_arshad=json.dumps(course_year_data_arshad),
        vazeiyat_data=json.dumps(vazeiyat_data, ensure_ascii=False),
        vazeiyat_data_404=json.dumps(vazeiyat_data_404, ensure_ascii=False),
        province_vazeiyat_data=json.dumps(province_vazeiyat_data, ensure_ascii=False)

    )
