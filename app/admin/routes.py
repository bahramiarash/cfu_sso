"""
Admin Panel Routes
Routes for admin panel functionality
"""
from flask import render_template, request, jsonify, redirect, url_for, flash, session, Response
from flask_login import login_required, current_user
from . import admin_bp
from .utils import admin_required, log_action, get_user_org_context
from models import User, AccessLevel as AccessLevelModel, UserType
from admin_models import DashboardAccess, AccessLog, DataSync, DashboardConfig, ChartConfig, TemplateVersion
from extensions import db
from sqlalchemy import or_, func
from dashboards.registry import DashboardRegistry
from datetime import datetime, timedelta
from jdatetime import datetime as jdatetime
import logging
import os
import shutil
from pathlib import Path
import requests
import subprocess
import json
from typing import Dict, Optional

logger = logging.getLogger(__name__)


def get_access_token_from_session():
    """Extract access token from session, handling both string and dict formats"""
    # Try access_token first (direct string)
    token = session.get('access_token') or session.get('auth_token')
    if token and isinstance(token, str):
        return token
    
    # Try sso_token (could be dict or string)
    sso_token = session.get('sso_token')
    if isinstance(sso_token, dict):
        return sso_token.get('access_token')
    elif isinstance(sso_token, str):
        return sso_token
    
    return None


# میکروسرویس‌ها و اطلاعات آنها
MICROSERVICES = {
    'auth-service': {
        'name': 'سرویس احراز هویت',
        'port': 5001,
        'url': 'http://auth-service:5001',
        'container': 'auth-service',
        'description': 'مدیریت احراز هویت SSO و JWT Token'
    },
    'admin-service': {
        'name': 'سرویس مدیریت',
        'port': 5002,
        'url': 'http://admin-service:5002',
        'container': 'admin-service',
        'description': 'مدیریت کاربران، دسترسی‌ها و همگام‌سازی داده'
    },
    'survey-service': {
        'name': 'سرویس نظرسنجی',
        'port': 5003,
        'url': 'http://survey-service:5003',
        'container': 'survey-service',
        'description': 'مدیریت نظرسنجی‌ها و پاسخ‌های کاربران'
    },
    'dashboard-service': {
        'name': 'سرویس داشبورد',
        'port': 5004,
        'url': 'http://dashboard-service:5004',
        'container': 'dashboard-service',
        'description': 'نمایش داشبوردهای تحلیلی و نمودارها'
    },
    'kanban-service': {
        'name': 'سرویس Kanban',
        'port': 5005,
        'url': 'http://kanban-service:5005',
        'container': 'kanban-service',
        'description': 'مدیریت پروژه‌ها و تسک‌ها'
    },
    'gateway-service': {
        'name': 'سرویس Gateway',
        'port': 5000,
        'url': 'http://gateway-service:5000',
        'container': 'gateway-service',
        'description': 'مسیریابی و Proxy به سایر سرویس‌ها'
    }
}

def check_service_health(service_name: str) -> Dict:
    """
    بررسی وضعیت یک میکروسرویس از طریق health endpoint
    """
    service_info = MICROSERVICES.get(service_name)
    if not service_info:
        return {
            'status': 'unknown',
            'error': f'Service {service_name} not found'
        }
    
    try:
        # Convert Docker hostnames to localhost for non-Docker environments
        health_url = service_info['url'].replace('auth-service', 'localhost')\
                                       .replace('admin-service', 'localhost')\
                                       .replace('survey-service', 'localhost')\
                                       .replace('dashboard-service', 'localhost')\
                                       .replace('kanban-service', 'localhost')\
                                       .replace('gateway-service', 'localhost')
        health_url = f"{health_url}/health"
        response = requests.get(health_url, timeout=5)
        
        if response.status_code == 200:
            try:
                health_data = response.json()
                return {
                    'status': 'healthy',
                    'status_code': response.status_code,
                    'response_time': response.elapsed.total_seconds(),
                    'data': health_data
                }
            except json.JSONDecodeError:
                return {
                    'status': 'healthy',
                    'status_code': response.status_code,
                    'response_time': response.elapsed.total_seconds(),
                    'data': {'message': response.text[:200]}
                }
        else:
            return {
                'status': 'unhealthy',
                'status_code': response.status_code,
                'error': f'Health check returned status {response.status_code}'
            }
    except requests.exceptions.Timeout:
        return {
            'status': 'timeout',
            'error': 'Health check request timed out'
        }
    except requests.exceptions.ConnectionError:
        return {
            'status': 'unreachable',
            'error': 'Could not connect to service'
        }
    except Exception as e:
        return {
            'status': 'error',
            'error': str(e)
        }

def check_docker_container_status(container_name: str) -> Dict:
    """
    بررسی وضعیت container از طریق docker ps
    """
    try:
        result = subprocess.run(
            ['docker', 'ps', '-a', '--filter', f'name={container_name}', '--format', '{{.Status}}|{{.Names}}'],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if result.returncode == 0 and result.stdout.strip():
            status_line = result.stdout.strip()
            if container_name in status_line:
                if 'Up' in status_line:
                    # Extract uptime
                    parts = status_line.split('|')
                    status = parts[0] if len(parts) > 0 else status_line
                    return {
                        'running': True,
                        'status': status
                    }
                else:
                    return {
                        'running': False,
                        'status': status_line.split('|')[0] if '|' in status_line else status_line
                    }
        
        return {
            'running': False,
            'status': 'Container not found'
        }
    except FileNotFoundError:
        return {
            'running': None,
            'status': 'Docker command not found'
        }
    except subprocess.TimeoutExpired:
        return {
            'running': None,
            'status': 'Docker command timeout'
        }
    except Exception as e:
        return {
            'running': None,
            'status': f'Error: {str(e)}'
        }

def restart_service(service_name: str) -> Dict:
    """
    Restart کردن یک میکروسرویس با استفاده از docker-compose
    """
    try:
        service_info = MICROSERVICES.get(service_name)
        if not service_info:
            logger.error(f"Service {service_name} not found in MICROSERVICES")
            return {
                'success': False,
                'error': f'Service {service_name} not found'
            }
        
        # پیدا کردن مسیر docker-compose.yml
        # __file__ = app/admin/routes.py
        # parent = app/admin
        # parent.parent = app
        # parent.parent.parent = project root
        compose_file = None
        current_file = Path(__file__).resolve()
        project_root = current_file.parent.parent.parent
        
        logger.info(f"Looking for docker-compose.yml starting from: {project_root}")
        
        # جستجو در دایرکتوری‌های مختلف (مسیرهای بیشتر)
        search_dirs = [
            project_root,  # c:\services\cert2
            project_root.parent,  # c:\services
            Path('/'),  # Root (for Unix)
            Path('C:/'),  # Windows C drive root
        ]
        
        # همچنین بررسی مسیرهای معمول
        if os.name == 'nt':  # Windows
            search_dirs.extend([
                Path('C:/services/cert2'),
                Path('C:/services'),
            ])
        
        for search_dir in search_dirs:
            try:
                compose_path = search_dir / 'docker-compose.yml'
                logger.debug(f"Checking for docker-compose.yml at: {compose_path}")
                if compose_path.exists() and compose_path.is_file():
                    compose_file = compose_path
                    logger.info(f"Found docker-compose.yml at: {compose_file}")
                    break
            except (OSError, PermissionError) as e:
                logger.debug(f"Cannot access {search_dir}: {e}")
                continue
        
        if not compose_file:
            logger.error(f"docker-compose.yml not found. Searched in: {search_dirs}")
            return {
                'success': False,
                'error': f'docker-compose.yml not found. Please ensure docker-compose.yml exists in the project root.'
            }
        
        # بررسی اینکه آیا docker-compose یا docker compose موجود است
        docker_compose_cmd = None
        docker_compose_variant = None
        
        # ابتدا بررسی docker compose (جدید)
        try:
            result = subprocess.run(
                ['docker', 'compose', 'version'],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                docker_compose_cmd = ['docker', 'compose']
                docker_compose_variant = 'docker compose'
                logger.info("Found docker compose (new syntax)")
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass
        
        # اگر docker compose پیدا نشد، بررسی docker-compose (قدیمی)
        if not docker_compose_cmd:
            try:
                result = subprocess.run(
                    ['docker-compose', '--version'],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                if result.returncode == 0:
                    docker_compose_cmd = ['docker-compose']
                    docker_compose_variant = 'docker-compose'
                    logger.info("Found docker-compose (old syntax)")
            except (FileNotFoundError, subprocess.TimeoutExpired):
                pass
        
        if not docker_compose_cmd:
            logger.error("Neither docker-compose nor docker compose command found")
            return {
                'success': False,
                'error': 'Neither docker-compose nor docker compose command found. Please install Docker Compose.'
            }
        
        # بررسی اینکه آیا service در docker-compose.yml وجود دارد (اختیاری)
        compose_data = None
        try:
            try:
                import yaml
                with open(compose_file, 'r', encoding='utf-8') as f:
                    compose_data = yaml.safe_load(f)
                    if 'services' not in compose_data or service_name not in compose_data.get('services', {}):
                        logger.warning(f"Service {service_name} not found in docker-compose.yml services")
                        # ادامه می‌دهیم - docker-compose خودش خطا را نشان می‌دهد
            except ImportError:
                logger.debug("yaml module not available, skipping service verification")
            except Exception as e:
                logger.warning(f"Could not parse docker-compose.yml to verify service: {e}")
                # ادامه می‌دهیم - docker-compose خودش خطا را نشان می‌دهد
        except Exception as e:
            logger.debug(f"Error checking docker-compose.yml: {e}")
        
        # اجرای دستور restart
        try:
            logger.info(f"Attempting restart with {docker_compose_variant} for service: {service_name}")
            cmd = docker_compose_cmd + ['-f', str(compose_file), 'restart', service_name]
            logger.debug(f"Command: {' '.join(cmd)}")
            logger.debug(f"Working directory: {compose_file.parent}")
            
            result = subprocess.run(
                cmd,
                cwd=compose_file.parent,
                capture_output=True,
                text=True,
                timeout=60
            )
            
            logger.info(f"{docker_compose_variant} command returncode: {result.returncode}")
            logger.debug(f"{docker_compose_variant} stdout: {result.stdout}")
            logger.debug(f"{docker_compose_variant} stderr: {result.stderr}")
            
            if result.returncode == 0:
                logger.info(f"Service {service_name} restarted successfully using {docker_compose_variant}")
                return {
                    'success': True,
                    'message': f'Service {service_name} restarted successfully',
                    'output': result.stdout
                }
            else:
                # استخراج پیام خطا
                error_output = result.stderr.strip() if result.stderr.strip() else result.stdout.strip()
                if not error_output:
                    error_output = 'Unknown error'
                
                # اگر خطا مربوط به service not found باشد، پیام بهتری بده
                if 'no such service' in error_output.lower() or ('service' in error_output.lower() and 'not found' in error_output.lower()):
                    if compose_data and 'services' in compose_data:
                        available_services = ", ".join(compose_data['services'].keys())
                        error_msg = f'Service "{service_name}" not found in docker-compose.yml. Available services: {available_services}'
                    else:
                        error_msg = f'Service "{service_name}" not found in docker-compose.yml. {error_output}'
                else:
                    error_msg = error_output
                
                logger.error(f"{docker_compose_variant} failed: {error_msg}")
                return {
                    'success': False,
                    'error': error_msg,
                    'returncode': result.returncode
                }
        except subprocess.TimeoutExpired:
            logger.error(f"Restart command timed out after 60 seconds for service: {service_name}")
            return {
                'success': False,
                'error': 'Restart command timed out after 60 seconds'
            }
        except FileNotFoundError:
            logger.error(f"Command not found: {docker_compose_variant}")
            return {
                'success': False,
                'error': f'Command not found: {docker_compose_variant}. Please install Docker Compose.'
            }
        except Exception as e:
            logger.error(f"Error running {docker_compose_variant}: {e}", exc_info=True)
            import traceback
            error_traceback = traceback.format_exc()
            logger.error(f"Full traceback: {error_traceback}")
            return {
                'success': False,
                'error': f'Error running {docker_compose_variant}: {str(e)}'
            }
    except Exception as e:
        logger.error(f"Fatal error in restart_service for {service_name}: {e}", exc_info=True)
        import traceback
        error_traceback = traceback.format_exc()
        logger.error(f"Full traceback: {error_traceback}")
        return {
            'success': False,
            'error': f'Fatal error: {str(e)}'
        }

# Color palettes for charts
COLOR_PALETTES = {
    'default': {
        'name': 'پیش‌فرض',
        'colors': [
            'rgba(255, 99, 132, 0.6)',
            'rgba(54, 162, 235, 0.6)',
            'rgba(255, 206, 86, 0.6)',
            'rgba(75, 192, 192, 0.6)',
            'rgba(153, 102, 255, 0.6)',
            'rgba(255, 159, 64, 0.6)',
            'rgba(201, 203, 207, 0.6)'
        ]
    },
    'warm': {
        'name': 'گرم',
        'colors': [
            'rgba(255, 99, 71, 0.6)',   # Tomato
            'rgba(255, 140, 0, 0.6)',   # Dark Orange
            'rgba(255, 165, 0, 0.6)',   # Orange
            'rgba(255, 20, 147, 0.6)',  # Deep Pink
            'rgba(220, 20, 60, 0.6)',   # Crimson
            'rgba(255, 69, 0, 0.6)',    # Red Orange
            'rgba(255, 105, 180, 0.6)'  # Hot Pink
        ]
    },
    'cool': {
        'name': 'سرد',
        'colors': [
            'rgba(70, 130, 180, 0.6)',  # Steel Blue
            'rgba(100, 149, 237, 0.6)', # Cornflower Blue
            'rgba(65, 105, 225, 0.6)',   # Royal Blue
            'rgba(30, 144, 255, 0.6)',   # Dodger Blue
            'rgba(0, 191, 255, 0.6)',    # Deep Sky Blue
            'rgba(72, 209, 204, 0.6)',   # Medium Turquoise
            'rgba(32, 178, 170, 0.6)'    # Light Sea Green
        ]
    },
    'pastel': {
        'name': 'پاستیلی',
        'colors': [
            'rgba(255, 182, 193, 0.6)',  # Light Pink
            'rgba(255, 218, 185, 0.6)',  # Peach Puff
            'rgba(221, 160, 221, 0.6)',  # Plum
            'rgba(176, 224, 230, 0.6)',  # Powder Blue
            'rgba(175, 238, 238, 0.6)',  # Pale Turquoise
            'rgba(144, 238, 144, 0.6)',   # Light Green
            'rgba(255, 228, 196, 0.6)'   # Bisque
        ]
    },
    'formal': {
        'name': 'رسمی',
        'colors': [
            'rgba(47, 79, 79, 0.6)',    # Dark Slate Gray
            'rgba(105, 105, 105, 0.6)',  # Dim Gray
            'rgba(128, 128, 128, 0.6)',  # Gray
            'rgba(169, 169, 169, 0.6)',  # Dark Gray
            'rgba(192, 192, 192, 0.6)',  # Silver
            'rgba(112, 128, 144, 0.6)',  # Slate Gray
            'rgba(119, 136, 153, 0.6)'   # Light Slate Gray
        ]
    },
    'vibrant': {
        'name': 'زنده',
        'colors': [
            'rgba(255, 0, 0, 0.6)',      # Red
            'rgba(0, 255, 0, 0.6)',      # Lime
            'rgba(0, 0, 255, 0.6)',      # Blue
            'rgba(255, 255, 0, 0.6)',    # Yellow
            'rgba(255, 0, 255, 0.6)',    # Magenta
            'rgba(0, 255, 255, 0.6)',    # Cyan
            'rgba(255, 128, 0, 0.6)'     # Orange
        ]
    },
    'ocean': {
        'name': 'اقیانوسی',
        'colors': [
            'rgba(0, 119, 190, 0.6)',    # Deep Blue
            'rgba(0, 150, 255, 0.6)',    # Bright Blue
            'rgba(64, 224, 208, 0.6)',   # Turquoise
            'rgba(0, 206, 209, 0.6)',    # Dark Turquoise
            'rgba(72, 209, 204, 0.6)',   # Medium Turquoise
            'rgba(95, 158, 160, 0.6)',   # Cadet Blue
            'rgba(176, 196, 222, 0.6)'   # Light Steel Blue
        ]
    }
}

def get_color_palette(palette_name='default'):
    """Get color palette by name, return default if not found"""
    return COLOR_PALETTES.get(palette_name, COLOR_PALETTES['default'])

# Helper function to apply chart configurations to HTML template
def validate_html(content: str) -> list:
    """Validate HTML code and return list of errors"""
    errors = []
    import re
    
    try:
        # Remove HTML comments first
        content_no_comments = re.sub(r'<!--.*?-->', '', content, flags=re.DOTALL)
        
        # Remove content inside <script> tags (we'll validate JS separately)
        script_pattern = r'<script[^>]*>.*?</script>'
        content_no_scripts = re.sub(script_pattern, '', content_no_comments, flags=re.DOTALL | re.IGNORECASE)
        
        # Remove content inside <style> tags (we'll validate CSS separately)
        style_pattern = r'<style[^>]*>.*?</style>'
        content_no_styles = re.sub(style_pattern, '', content_no_scripts, flags=re.DOTALL | re.IGNORECASE)
        
        # Remove Jinja2 template syntax blocks ({% ... %}, {{ ... }}, {# ... #})
        jinja_blocks = r'\{[%#]?[^}]*[%#]?\}'
        content_clean = re.sub(jinja_blocks, '', content_no_styles, flags=re.DOTALL)
        
        # Check for malformed tags first (tags without closing >)
        # Look for <tag that doesn't have > before newline or end of content
        lines = content_clean.split('\n')
        for line_idx, line in enumerate(lines):
            # Find all < that might be start of tags
            pos = 0
            while pos < len(line):
                tag_start = line.find('<', pos)
                if tag_start == -1:
                    break
                
                # Check if this looks like a tag (starts with letter after <)
                if tag_start + 1 < len(line) and line[tag_start + 1].isalpha():
                    # Find where this tag should end
                    tag_end = line.find('>', tag_start)
                    if tag_end == -1:
                        # Tag doesn't close on this line - it's malformed
                        tag_match = re.search(r'<([a-zA-Z][a-zA-Z0-9]*)', line[tag_start:])
                        if tag_match:
                            tag_name = tag_match.group(1)
                            # Check if it's not a self-closing tag pattern
                            if not line[tag_start:].strip().endswith('/>'):
                                errors.append({
                                    'line': line_idx + 1,
                                    'message': f'تگ ناقص: <{tag_name}> (نشان > گم شده)',
                                    'suggestion': f'تگ <{tag_name}> را کامل کنید و نشان > را اضافه کنید: <{tag_name} ...>'
                                })
                        pos = len(line)
                    else:
                        pos = tag_end + 1
                else:
                    pos = tag_start + 1
        
        # Check for invalid tag names (tags starting with numbers or special chars, but not comments or doctype)
        invalid_tag_pattern = r'<(?![!/?])([^a-zA-Z/!][^>]*)>'
        for match in re.finditer(invalid_tag_pattern, content_clean):
            # Skip if it's a valid comment or doctype
            tag_content = match.group(0)
            if tag_content.startswith('<!--') or tag_content.startswith('<!DOCTYPE'):
                continue
            line_num = content[:match.start()].count('\n') + 1
            errors.append({
                'line': line_num,
                'message': f'نام تگ نامعتبر: {tag_content[:50]}',
                'suggestion': 'نام تگ باید با حرف انگلیسی شروع شود: <div>, <span>, <p> و غیره'
            })
        
        # Check for tags with spaces before closing bracket (common typo: <div > instead of <div>)
        space_before_close_pattern = r'<([a-zA-Z][a-zA-Z0-9]*)\b[^>]*\s+>'
        for match in re.finditer(space_before_close_pattern, content_clean):
            tag_name = match.group(1)
            tag_full = match.group(0)
            # Only flag if there's a space right before >
            if tag_full.rstrip().endswith(' >'):
                line_num = content[:match.start()].count('\n') + 1
                errors.append({
                    'line': line_num,
                    'message': f'فاصله اضافی قبل از > در تگ <{tag_name}>',
                    'suggestion': f'فاصله اضافی را حذف کنید: <{tag_name} ...> (بدون فاصله قبل از >)'
                })
        
        # Now check for unclosed tags in cleaned content
        open_tags = []
        tag_pattern = r'<(/?)([a-zA-Z][a-zA-Z0-9]*)\b[^>]*>'
        
        # Self-closing tags that don't need closing
        self_closing_tags = {
            'br', 'hr', 'img', 'input', 'meta', 'link', 'area', 'base', 'col', 
            'embed', 'source', 'track', 'wbr', 'param', 'keygen', 'menuitem'
        }
        
        for match in re.finditer(tag_pattern, content_clean):
            is_closing = match.group(1) == '/'
            tag_name = match.group(2).lower()
            
            # Check if it's a self-closing tag (either in list or has />)
            tag_full = match.group(0)
            is_self_closing = tag_name in self_closing_tags or tag_full.endswith('/>')
            
            if is_self_closing:
                continue
            
            if is_closing:
                # Find matching opening tag
                if open_tags and open_tags[-1] == tag_name:
                    open_tags.pop()
                elif tag_name in [t for t in open_tags]:
                    # Mismatched closing tag - find line number in original content
                    line_num = content[:match.start()].count('\n') + 1
                    errors.append({
                        'line': line_num,
                        'message': f'تگ بسته نامطابق: </{tag_name}>',
                        'suggestion': f'مطمئن شوید که تگ <{tag_name}> قبل از این تگ بسته شده است.'
                    })
            else:
                open_tags.append(tag_name)
        
        # Check for remaining unclosed tags (but ignore common template tags)
        # Filter out tags that are commonly used in templates and might be intentionally left open
        template_tags = {'extends', 'block', 'endblock', 'if', 'endif', 'for', 'endfor', 'macro', 'endmacro'}
        
        for tag in open_tags:
            if tag not in template_tags:
                # Try to find where this tag was opened in original content
                tag_open_pattern = rf'<{re.escape(tag)}\b[^>]*>'
                matches = list(re.finditer(tag_open_pattern, content_clean, re.IGNORECASE))
                if matches:
                    last_match = matches[-1]
                    line_num = content[:last_match.start()].count('\n') + 1
                    errors.append({
                        'line': line_num,
                        'message': f'تگ باز نشده: <{tag}>',
                        'suggestion': f'تگ <{tag}> را ببندید: </{tag}>'
                    })
                else:
                    errors.append({
                        'line': None,
                        'message': f'تگ باز نشده: <{tag}>',
                        'suggestion': f'تگ <{tag}> را ببندید: </{tag}>'
                    })
        
        # Check for common HTML errors in original content (not cleaned)
        # Missing closing quotes in attributes
        # This is a more careful check - look for = followed by quote but no closing quote on same line
        attr_pattern = r'=\s*["\']([^"\']*?)(?:\n|$)'
        for match in re.finditer(attr_pattern, content, re.MULTILINE):
            attr_value = match.group(1)
            # If the value doesn't end with a quote and the line doesn't continue, it's an error
            if not attr_value.endswith('"') and not attr_value.endswith("'"):
                # Check if this is actually inside a script or style tag
                pos = match.start()
                before_pos = content[:pos]
                # Count script and style tags before this position
                script_before = len(re.findall(r'<script[^>]*>', before_pos, re.IGNORECASE))
                script_close_before = len(re.findall(r'</script>', before_pos, re.IGNORECASE))
                style_before = len(re.findall(r'<style[^>]*>', before_pos, re.IGNORECASE))
                style_close_before = len(re.findall(r'</style>', before_pos, re.IGNORECASE))
                
                # Only report if we're not inside a script or style tag
                if script_before == script_close_before and style_before == style_close_before:
                    line_num = content[:match.start()].count('\n') + 1
                    errors.append({
                        'line': line_num,
                        'message': 'نقل قول بسته نشده در attribute',
                        'suggestion': 'مطمئن شوید که تمام attribute ها نقل قول بسته دارند: attribute="value"'
                    })
        
    except Exception as e:
        errors.append({
            'line': None,
            'message': f'خطا در بررسی HTML: {str(e)}',
            'suggestion': None
        })
    
    return errors


def validate_css(content: str) -> list:
    """Validate CSS code and return list of errors"""
    errors = []
    import re
    
    try:
        # Extract CSS from style tags and inline styles
        css_pattern = r'<style[^>]*>(.*?)</style>'
        style_matches = re.finditer(css_pattern, content, re.DOTALL | re.IGNORECASE)
        
        css_content = ''
        for match in style_matches:
            css_content += match.group(1) + '\n'
        
        # Also extract inline styles
        inline_style_pattern = r'style\s*=\s*["\']([^"\']*)["\']'
        inline_matches = re.finditer(inline_style_pattern, content, re.IGNORECASE)
        for match in inline_matches:
            css_content += match.group(1) + '\n'
        
        if not css_content.strip():
            return errors  # No CSS to validate
        
        # Check for unclosed braces
        brace_count = 0
        lines = css_content.split('\n')
        for i, line in enumerate(lines):
            brace_count += line.count('{')
            brace_count -= line.count('}')
            
            if brace_count < 0:
                errors.append({
                    'line': i + 1,
                    'message': 'بریس بسته اضافی }',
                    'suggestion': 'بریس اضافی را حذف کنید یا بریس باز { را اضافه کنید.'
                })
        
        if brace_count > 0:
            errors.append({
                'line': None,
                'message': f'{brace_count} بریس باز بسته نشده',
                'suggestion': 'تمام بریس‌های باز { را ببندید: }'
            })
        
        # Check for common CSS errors
        # Missing semicolons (basic check)
        selector_pattern = r'([^{]+)\{([^}]+)\}'
        for match in re.finditer(selector_pattern, css_content):
            properties = match.group(2)
            # Check if last property has semicolon (excluding whitespace and closing brace)
            props = [p.strip() for p in properties.split(';') if p.strip()]
            if props:
                last_prop = props[-1]
                if not last_prop.endswith(';') and ':' in last_prop:
                    # This might be intentional, but we'll flag it
                    line_num = css_content[:match.start()].count('\n') + 1
                    errors.append({
                        'line': line_num,
                        'message': 'نقطه‌ویرگول در انتهای property ممکن است گم شده باشد',
                        'suggestion': 'مطمئن شوید که تمام property ها با ; تمام می‌شوند: property: value;'
                    })
        
        # Check for invalid property names (basic)
        invalid_props = re.finditer(r'([a-zA-Z-]+)\s*:\s*[^;}]*(?:;|})', css_content)
        for match in invalid_props:
            prop_name = match.group(1).strip()
            # Common typos
            typos = {
                'backgound': 'background',
                'backgroun': 'background',
                'widht': 'width',
                'heigth': 'height',
                'colr': 'color',
                'font-szie': 'font-size',
                'margn': 'margin',
                'paddng': 'padding'
            }
            if prop_name.lower() in typos:
                line_num = css_content[:match.start()].count('\n') + 1
                errors.append({
                    'line': line_num,
                    'message': f'نام property اشتباه: {prop_name}',
                    'suggestion': f'احتمالاً منظور شما {typos[prop_name.lower()]} بوده است.'
                })
        
    except Exception as e:
        errors.append({
            'line': None,
            'message': f'خطا در بررسی CSS: {str(e)}',
            'suggestion': None
        })
    
    return errors


def validate_javascript(content: str) -> list:
    """Validate JavaScript code and return list of errors"""
    errors = []
    import re
    
    try:
        # First check for unclosed script tags
        script_open_pattern = r'<script[^>]*>'
        script_close_pattern = r'</script>'
        
        script_opens = list(re.finditer(script_open_pattern, content, re.IGNORECASE))
        script_closes = list(re.finditer(script_close_pattern, content, re.IGNORECASE))
        
        # Check for mismatched script tags
        open_count = 0
        for script_open in script_opens:
            # Check if this script has src attribute (external script, might not have closing tag in content)
            script_tag = content[script_open.start():script_open.end() + 100]
            if 'src=' not in script_tag.lower():
                open_count += 1
        
        close_count = len(script_closes)
        
        if open_count > close_count:
            # Find the unclosed script tag
            for i, script_open in enumerate(script_opens):
                script_tag = content[script_open.start():script_open.end() + 100]
                if 'src=' not in script_tag.lower():
                    # Check if there's a closing tag after this
                    has_close = False
                    for script_close in script_closes:
                        if script_close.start() > script_open.end():
                            has_close = True
                            break
                    if not has_close:
                        line_num = content[:script_open.start()].count('\n') + 1
                        errors.append({
                            'line': line_num,
                            'message': 'تگ <script> بسته نشده',
                            'suggestion': 'تگ <script> را ببندید: </script>'
                        })
        
        # Extract JavaScript from script tags
        script_pattern = r'<script[^>]*>(.*?)</script>'
        script_matches = re.finditer(script_pattern, content, re.DOTALL | re.IGNORECASE)
        
        js_content = ''
        script_starts = []
        for match in script_matches:
            script_content = match.group(1)
            # Skip if it's an external script (has src attribute)
            script_tag = content[match.start():match.start() + 200]
            if 'src=' in script_tag.lower():
                continue
            
            # Store where this script starts in original content
            script_starts.append(content[:match.start()].count('\n') + 1)
            js_content += script_content + '\n'
        
        if not js_content.strip():
            return errors  # No JS to validate
        
        # Check for unclosed braces
        brace_count = 0
        paren_count = 0
        bracket_count = 0
        lines = js_content.split('\n')
        
        for i, line in enumerate(lines):
            # Count braces, parentheses, brackets
            brace_count += line.count('{')
            brace_count -= line.count('}')
            paren_count += line.count('(')
            paren_count -= line.count(')')
            bracket_count += line.count('[')
            bracket_count -= line.count(']')
            
            if brace_count < 0:
                line_num = script_starts[0] + i if script_starts else i + 1
                errors.append({
                    'line': line_num,
                    'message': 'بریس بسته اضافی }',
                    'suggestion': 'بریس اضافی را حذف کنید یا بریس باز { را اضافه کنید.'
                })
            if paren_count < 0:
                line_num = script_starts[0] + i if script_starts else i + 1
                errors.append({
                    'line': line_num,
                    'message': 'پرانتز بسته اضافی )',
                    'suggestion': 'پرانتز اضافی را حذف کنید یا پرانتز باز ( را اضافه کنید.'
                })
            if bracket_count < 0:
                line_num = script_starts[0] + i if script_starts else i + 1
                errors.append({
                    'line': line_num,
                    'message': 'براکت بسته اضافی ]',
                    'suggestion': 'براکت اضافی را حذف کنید یا براکت باز [ را اضافه کنید.'
                })
        
        if brace_count > 0:
            errors.append({
                'line': None,
                'message': f'{brace_count} بریس باز بسته نشده',
                'suggestion': 'تمام بریس‌های باز { را ببندید: }'
            })
        if paren_count > 0:
            errors.append({
                'line': None,
                'message': f'{paren_count} پرانتز باز بسته نشده',
                'suggestion': 'تمام پرانتزهای باز ( را ببندید: )'
            })
        if bracket_count > 0:
            errors.append({
                'line': None,
                'message': f'{bracket_count} براکت باز بسته نشده',
                'suggestion': 'تمام براکت‌های باز [ را ببندید: ]'
            })
        
        # Check for common JS errors using regex
        # Missing semicolons (optional but good practice)
        # Check for common typos
        common_typos = {
            'fucntion': 'function',
            'funtion': 'function',
            'fucnction': 'function',
            'retun': 'return',
            'retrun': 'return',
            'varibale': 'variable',
            'consol': 'console',
            'docuemnt': 'document',
            'getElemenById': 'getElementById',
            'getElemenByClass': 'getElementsByClassName',
            'addEventListner': 'addEventListener'
        }
        
        for typo, correct in common_typos.items():
            typo_pattern = r'\b' + re.escape(typo) + r'\b'
            for match in re.finditer(typo_pattern, js_content, re.IGNORECASE):
                line_num = js_content[:match.start()].count('\n') + 1
                if script_starts:
                    line_num = script_starts[0] + line_num - 1
                errors.append({
                    'line': line_num,
                    'message': f'اشتباه تایپی: {match.group(0)}',
                    'suggestion': f'احتمالاً منظور شما {correct} بوده است.'
                })
        
        # Check for undefined variables (basic check - look for common patterns)
        # This is a simple heuristic, not a full parser
        var_pattern = r'\b(var|let|const)\s+([a-zA-Z_$][a-zA-Z0-9_$]*)\s*='
        declared_vars = set()
        for match in re.finditer(var_pattern, js_content):
            declared_vars.add(match.group(2))
        
        # Check for common undefined references
        undefined_patterns = [
            (r'\bconsole\.log\s*\(', 'console.log'),
            (r'\bdocument\.', 'document'),
            (r'\bwindow\.', 'window'),
        ]
        
        # Check for common JavaScript syntax errors
        # Check for malformed property assignments (like "borderCo, fill: truelor:")
        malformed_prop_pattern = r'([a-zA-Z_$][a-zA-Z0-9_$]*)\s*,\s*([a-zA-Z_$][a-zA-Z0-9_$]*)\s*:\s*([^,}]+)'
        for match in re.finditer(malformed_prop_pattern, js_content):
            prop1 = match.group(1)
            prop2 = match.group(2)
            value = match.group(3).strip()
            # Check if this looks like a typo (property name cut off and continued)
            if len(prop1) < 8 and prop2 in ['fill', 'color', 'width', 'height', 'size']:
                # Find line number in original content
                match_pos = match.start()
                # Find which script this belongs to
                line_offset = 0
                for i, script_start in enumerate(script_starts):
                    if i < len(script_starts) - 1:
                        next_start = script_starts[i + 1] if i + 1 < len(script_starts) else len(content)
                    else:
                        next_start = len(content)
                    # This is approximate - we'd need to track exact positions
                    pass
                
                # Try to find the line in js_content
                line_in_js = js_content[:match_pos].count('\n') + 1
                if script_starts:
                    # Approximate line number
                    line_num = script_starts[0] + line_in_js - 1
                else:
                    line_num = line_in_js
                
                errors.append({
                    'line': line_num,
                    'message': f'خطای syntax: {prop1}, {prop2}: {value[:30]}',
                    'suggestion': f'احتمالاً {prop1} ناقص است. بررسی کنید که آیا {prop1}Color یا {prop1}Width و غیره منظور بوده است.'
                })
        
        # Check for common typos in property names
        common_js_typos = {
            'borderCo': 'borderColor',
            'backgound': 'background',
            'backgroun': 'background',
            'widht': 'width',
            'heigth': 'height',
            'colr': 'color',
            'fucntion': 'function',
            'retun': 'return',
            'consol': 'console',
            'docuemnt': 'document'
        }
        
        for typo, correct in common_js_typos.items():
            typo_pattern = r'\b' + re.escape(typo) + r'\b'
            for match in re.finditer(typo_pattern, js_content, re.IGNORECASE):
                line_in_js = js_content[:match.start()].count('\n') + 1
                if script_starts:
                    line_num = script_starts[0] + line_in_js - 1
                else:
                    line_num = line_in_js
                errors.append({
                    'line': line_num,
                    'message': f'اشتباه تایپی: {match.group(0)}',
                    'suggestion': f'احتمالاً منظور شما {correct} بوده است.'
                })
        
        # Try to parse with basic syntax check
        # Check for string quote mismatches
        single_quotes = js_content.count("'")
        double_quotes = js_content.count('"')
        # This is a very basic check - real validation would need a proper parser
        
    except Exception as e:
        errors.append({
            'line': None,
            'message': f'خطا در بررسی JavaScript: {str(e)}',
            'suggestion': None
        })
    
    return errors


def apply_chart_configs_to_html(template_path: Path, chart_configs: list) -> bool:
    """
    Apply chart configurations to HTML template file.
    Updates chart types, titles, and other settings in the JavaScript code.
    
    Args:
        template_path: Path to the HTML template file
        chart_configs: List of chart configuration dictionaries
        
    Returns:
        True if successful, False otherwise
    """
    try:
        # Read template content
        with open(template_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        original_content = content
        import re
        
        # Collect all changes first, then apply them from end to start
        # This prevents position shifts when making multiple replacements
        changes = []  # List of (start_pos, end_pos, new_text) tuples
        
        # Apply configurations to each chart
        for chart_config in chart_configs:
            chart_id = chart_config.get('chart_id')
            if not chart_id:
                continue
            
            chart_type = chart_config.get('chart_type')
            title = chart_config.get('title')
            show_legend = chart_config.get('show_legend')
            show_labels = chart_config.get('show_labels')
            is_visible = chart_config.get('is_visible')
            allow_export = chart_config.get('allow_export')
            color_palette = chart_config.get('color_palette', 'default')
            
            logger.info(f"Processing chart {chart_id}: type={chart_type}, title={title}, visible={is_visible}, labels={show_labels}, legend={show_legend}, export={allow_export}, palette={color_palette}")
            
            # 1. Update chart type in JavaScript
            # Find getElementById for this chart_id, then find the Chart initialization after it
            # Use exact match to ensure chart_id is not part of another id
            escaped_chart_id = re.escape(chart_id)
            # Pattern: getElementById('chart_id') where chart_id is exact match (not part of longer id)
            # We use negative lookahead to ensure chart_id is not followed by alphanumeric or underscore
            ctx_pattern = rf'getElementById\s*\([\'"]{escaped_chart_id}(?![a-zA-Z0-9_])[\'"]\)'
            
            # Find all matches and verify we get the exact one
            all_matches = list(re.finditer(ctx_pattern, content))
            ctx_match = None
            
            if all_matches:
                # Verify each match to ensure the extracted ID is exactly chart_id
                # This is critical to prevent 'genderChart' from matching 'genderChart404'
                logger.info(f"apply_chart_configs_to_html: Found {len(all_matches)} potential matches for chart_id '{chart_id}'")
                for i, match in enumerate(all_matches):
                    full_match = match.group(0)
                    logger.debug(f"apply_chart_configs_to_html: Checking match {i+1}: {full_match[:100]}")
                    
                    # Extract the ID directly from the match using a simpler, more reliable method
                    # Find all quoted strings in the match and verify one is exactly chart_id
                    quoted_id_pattern = rf'[\'"]([^\'"]+)[\'"]'
                    quoted_matches = list(re.finditer(quoted_id_pattern, full_match))
                    
                    found_exact_match = False
                    for quoted_match in quoted_matches:
                        extracted_id = quoted_match.group(1)  # Get the content inside quotes
                        logger.debug(f"apply_chart_configs_to_html: Match {i+1} found quoted ID: '{extracted_id}'")
                        
                        # CRITICAL CHECK: extracted ID must be exactly chart_id
                        # This prevents 'genderChart' from matching 'genderChart404'
                        if extracted_id == chart_id:
                            ctx_match = match
                            found_exact_match = True
                            logger.info(f"apply_chart_configs_to_html: ✓ Found exact match for chart_id '{chart_id}' at position {match.start()}")
                            break
                        elif chart_id in extracted_id and extracted_id != chart_id:
                            # This is a substring match (e.g., 'genderChart' in 'genderChart404')
                            logger.warning(f"apply_chart_configs_to_html: ✗ Match {i+1} rejected: extracted_id '{extracted_id}' contains '{chart_id}' but is not exact match")
                    
                    if found_exact_match:
                        break
                
                # DO NOT use fallback - if no exact match, skip this chart
                if not ctx_match:
                    logger.error(f"apply_chart_configs_to_html: ✗ No exact match found for chart_id '{chart_id}'. Skipping this chart to prevent incorrect updates.")
                    for i, match in enumerate(all_matches[:3]):
                        logger.error(f"  Rejected match {i+1}: {match.group(0)[:150]}")
                    # Skip this chart - don't try to update it
                    continue
            
            if not ctx_match:
                logger.warning(f"Chart {chart_id} not found in template. Searching for canvas element...")
                # Try to find canvas element directly
                # Use exact match to ensure chart_id is not part of another id
                escaped_chart_id = re.escape(chart_id)
                canvas_pattern = rf'<canvas[^>]*id\s*=\s*["\']{escaped_chart_id}(?![a-zA-Z0-9_])["\']'
                canvas_match = re.search(canvas_pattern, content, re.IGNORECASE)
                if canvas_match:
                    logger.info(f"Found canvas element for {chart_id}, but no getElementById. Chart may be initialized differently.")
                else:
                    logger.error(f"Chart {chart_id} not found in template at all!")
                    continue
            
            if ctx_match and chart_type:
                # Find the Chart initialization after this context
                start_pos = ctx_match.end()
                # Look for "new Chart" within next 2000 characters
                chart_block = content[start_pos:start_pos + 2000]
                chart_init_match = re.search(r'new\s+Chart\s*\([^,]+,\s*\{', chart_block)
                
                if chart_init_match:
                    # Find the type: 'xxx' pattern within this Chart initialization
                    chart_start_in_block = chart_init_match.end()
                    chart_init_full = chart_block[chart_start_in_block:]
                    
                    # Find type: 'xxx' pattern - try multiple patterns
                    type_patterns = [
                        r"type\s*:\s*['\"]([^'\"]+)['\"]",  # type: 'pie'
                        r"type\s*:\s*([a-zA-Z]+)\s*[,}]",  # type: pie,
                        r"['\"]type['\"]\s*:\s*['\"]([^'\"]+)['\"]",  # "type": "pie"
                    ]
                    
                    type_match = None
                    for pattern in type_patterns:
                        type_match = re.search(pattern, chart_init_full)
                        if type_match:
                            break
                    
                    if type_match:
                        old_type = type_match.group(1)
                        # For area charts, we need to use 'line' type in Chart.js with fill: true
                        # So if chart_type is 'area', we write 'line' to the file
                        js_chart_type = 'line' if chart_type == 'area' else chart_type
                        
                        if old_type != js_chart_type:
                            # Calculate absolute position
                            absolute_pos = start_pos + chart_start_in_block + type_match.start()
                            type_full_match = type_match.group(0)
                            # Create replacement - preserve quotes and format
                            if "'" in type_full_match:
                                new_type = type_full_match.replace(old_type, js_chart_type)
                            elif '"' in type_full_match:
                                new_type = type_full_match.replace(old_type, js_chart_type)
                            else:
                                # No quotes, add them
                                new_type = f"type: '{js_chart_type}'"
                            
                            changes.append((absolute_pos, absolute_pos + len(type_full_match), new_type))
                            logger.info(f"Queued chart type update for {chart_id}: {old_type} -> {js_chart_type} (DB type: {chart_type})")
                            
                            # If this is an area chart, ensure fill: true is set in datasets
                            if chart_type == 'area':
                                # Find the datasets array and ensure fill: true is present
                                # Look for datasets array after the type definition
                                dataset_section = chart_init_full[type_match.end():]
                                # Check if fill property exists
                                fill_pattern = r'fill\s*:\s*(true|false)'
                                fill_match = re.search(fill_pattern, dataset_section)
                                
                                if not fill_match:
                                    # Find the datasets array and add fill: true
                                    datasets_pattern = r'datasets\s*:\s*\['
                                    datasets_match = re.search(datasets_pattern, dataset_section)
                                    if datasets_match:
                                        # Find the first dataset object
                                        dataset_obj_pattern = r'\{[^}]*\}'
                                        dataset_obj_match = re.search(dataset_obj_pattern, dataset_section[datasets_match.end():])
                                        if dataset_obj_match:
                                            # Check if fill is already in the dataset object
                                            dataset_obj = dataset_obj_match.group(0)
                                            if 'fill' not in dataset_obj:
                                                # Add fill: true before the closing brace
                                                fill_insert_pos = absolute_pos + chart_start_in_block + type_match.end() + datasets_match.end() + dataset_obj_match.end() - 1
                                                changes.append((fill_insert_pos, fill_insert_pos, ', fill: true'))
                                                logger.info(f"Queued fill: true addition for area chart {chart_id}")
                                elif fill_match and fill_match.group(1) == 'false':
                                    # Update fill: false to fill: true
                                    fill_absolute_pos = absolute_pos + chart_start_in_block + type_match.end() + fill_match.start()
                                    changes.append((fill_absolute_pos, fill_absolute_pos + len(fill_match.group(0)), 'fill: true'))
                                    logger.info(f"Queued fill update for area chart {chart_id}: false -> true")
                        else:
                            logger.debug(f"Chart type for {chart_id} already correct: {js_chart_type} (DB type: {chart_type})")
                            
                            # Even if type is correct, ensure fill: true for area charts
                            if chart_type == 'area':
                                dataset_section = chart_init_full[type_match.end():]
                                fill_pattern = r'fill\s*:\s*(true|false)'
                                fill_match = re.search(fill_pattern, dataset_section)
                                
                                if not fill_match:
                                    datasets_pattern = r'datasets\s*:\s*\['
                                    datasets_match = re.search(datasets_pattern, dataset_section)
                                    if datasets_match:
                                        dataset_obj_pattern = r'\{[^}]*\}'
                                        dataset_obj_match = re.search(dataset_obj_pattern, dataset_section[datasets_match.end():])
                                        if dataset_obj_match:
                                            dataset_obj = dataset_obj_match.group(0)
                                            if 'fill' not in dataset_obj:
                                                fill_insert_pos = absolute_pos + chart_start_in_block + type_match.end() + datasets_match.end() + dataset_obj_match.end() - 1
                                                changes.append((fill_insert_pos, fill_insert_pos, ', fill: true'))
                                                logger.info(f"Queued fill: true addition for area chart {chart_id} (type already correct)")
                                elif fill_match and fill_match.group(1) == 'false':
                                    fill_absolute_pos = absolute_pos + chart_start_in_block + type_match.end() + fill_match.start()
                                    changes.append((fill_absolute_pos, fill_absolute_pos + len(fill_match.group(0)), 'fill: true'))
                                    logger.info(f"Queued fill update for area chart {chart_id}: false -> true (type already correct)")
                else:
                    logger.warning(f"Could not find Chart initialization for {chart_id}")
            else:
                if not ctx_match:
                    logger.warning(f"Could not find getElementById for chart {chart_id}")
                if not chart_type:
                    logger.warning(f"No chart_type provided for {chart_id}")
            
            # 2. Update chart title in h4/h5 tags before canvas
            if title:
                # Find h4/h5 tag that appears before the canvas with this chart_id
                # Pattern: <h4/h5>...</h4/h5> followed by canvas with id="chart_id"
                # Use exact match to ensure chart_id is not part of another id
                escaped_chart_id = re.escape(chart_id)
                title_section_pattern = rf'(<h[45][^>]*class=["\'][^"\']*mb-3[^"\']*["\'][^>]*>)([^<]+)(</h[45]>)(\s*<canvas[^>]*id=["\']{escaped_chart_id}(?![a-zA-Z0-9_])["\'])'
                title_match = re.search(title_section_pattern, content, re.DOTALL | re.IGNORECASE)
                
                if title_match:
                    current_title = title_match.group(2).strip()
                    if current_title != title:
                        # Replace the title text
                        title_start = title_match.start(2)
                        title_end = title_match.end(2)
                        changes.append((title_start, title_end, title))
                        logger.info(f"Queued title update for {chart_id}: '{current_title}' -> '{title}'")
                else:
                    logger.warning(f"Could not find title section for chart {chart_id}")
            
            # 3. Update legend display in plugins section
            if show_legend is not None:
                # Find the Chart initialization for this chart and update legend.display
                if ctx_match:
                    start_pos = ctx_match.end()
                    # Search in a larger block to find the entire Chart initialization
                    chart_block = content[start_pos:start_pos + 10000]  # Increased from 3000 to 10000
                    
                    # Search for ALL legend blocks in the entire chart_block (not just plugins section)
                    # This ensures we find all duplicates regardless of structure
                    legend_starts = list(re.finditer(r'legend\s*:\s*\{', chart_block, re.IGNORECASE))
                    logger.info(f"Found {len(legend_starts)} legend blocks in chart block for {chart_id}")
                        
                    all_legend_matches = []
                    for idx, legend_start in enumerate(legend_starts):
                        # Find the matching closing brace for this legend block
                        block_start_rel = legend_start.end()  # Relative to chart_block
                        block_content = chart_block[block_start_rel:]
                        brace_count = 1
                        block_end_rel = block_start_rel
                        found_end = False
                        for i, char in enumerate(block_content):
                            if char == '{':
                                brace_count += 1
                            elif char == '}':
                                brace_count -= 1
                                if brace_count == 0:
                                    block_end_rel = block_start_rel + i
                                    found_end = True
                                    break
                        
                        if not found_end:
                            logger.warning(f"Could not find closing brace for legend block {idx + 1} in {chart_id}")
                            continue
                        
                        # Search for display: true/false within this block
                        block_text = chart_block[block_start_rel:block_end_rel]
                        display_match = re.search(r'display\s*:\s*(true|false)\b', block_text, re.IGNORECASE)
                        if display_match:
                            # Calculate absolute position: start_pos + block_start_rel + display position
                            display_pos_abs = start_pos + block_start_rel + display_match.start(1)
                            display_value = display_match.group(1).lower()  # Normalize to lowercase
                            class MockMatch:
                                def __init__(self, pos, value, idx):
                                    self.start = lambda: pos
                                    self.group = lambda n: value if n == 1 else None
                                    self.index = idx
                            all_legend_matches.append(MockMatch(display_pos_abs, display_value, idx))
                            logger.debug(f"Found display in legend block {idx + 1}: {display_value} at absolute position {display_pos_abs}")
                        else:
                            logger.debug(f"Legend block {idx + 1} has no display property")
                    
                    # After processing all legend blocks, update them
                    if all_legend_matches:
                        # Update all occurrences - use a more aggressive approach to find ALL display values
                        logger.info(f"Found {len(all_legend_matches)} legend display settings to update for {chart_id}")
                        
                        # Set the target value - we want ALL legend display values to be this
                        new_value = 'true' if show_legend else 'false'
                        
                        # Find all legend blocks and update ALL display values within them
                        # Force update all found legend blocks to the new value, regardless of current value
                        queued_positions = set()
                        for legend_match in all_legend_matches:
                            old_value = legend_match.group(1)
                            logger.debug(f"Legend block {legend_match.index + 1} for {chart_id}: old_value='{old_value}', new_value='{new_value}'")
                            
                            # Always update to new_value, regardless of current value
                            absolute_pos = legend_match.start()
                            
                            # Skip if we already queued this position
                            if absolute_pos in queued_positions:
                                logger.debug(f"Skipping duplicate position {absolute_pos} for legend block {legend_match.index + 1}")
                                continue
                            
                            # Get the actual old value length from the content to handle case variations
                            old_value_from_content = content[absolute_pos:absolute_pos + 10].lower()
                            if 'true' in old_value_from_content:
                                actual_old_len = 4  # 'true'
                            elif 'false' in old_value_from_content:
                                actual_old_len = 5  # 'false'
                            else:
                                actual_old_len = len(old_value)
                            
                            changes.append((absolute_pos, absolute_pos + actual_old_len, new_value))
                            queued_positions.add(absolute_pos)
                            logger.info(f"Queued legend display update for {chart_id}: '{old_value}' -> '{new_value}' (legend block {legend_match.index + 1}) at position {absolute_pos}")
                        
                        # Additional pass: find ALL display: true/false patterns in legend blocks
                        # This ensures we catch ALL display values, regardless of current value
                        # Track positions we've already queued
                        queued_positions = {c[0] for c in changes}
                        
                        # Find all "legend: {" blocks and update ALL display values within them
                        all_legend_blocks = list(re.finditer(r'legend\s*:\s*\{', chart_block, re.IGNORECASE))
                        additional_count = 0
                        for legend_block_match in all_legend_blocks:
                            # Find the closing brace for this legend block
                            block_start = legend_block_match.end()
                            block_content = chart_block[block_start:]
                            brace_count = 1
                            block_end = block_start
                            found_end = False
                            for i, char in enumerate(block_content):
                                if char == '{':
                                    brace_count += 1
                                elif char == '}':
                                    brace_count -= 1
                                    if brace_count == 0:
                                        block_end = block_start + i
                                        found_end = True
                                        break
                            
                            if not found_end:
                                continue
                            
                            # Search for ANY display: true/false within this block
                            block_text = chart_block[block_start:block_end]
                            display_match = re.search(r'display\s*:\s*(true|false)\b', block_text, re.IGNORECASE)
                            if display_match:
                                # Calculate absolute position: start_pos + block_start + position of value
                                display_value_pos_in_block = display_match.start(1)
                                display_pos_abs = start_pos + block_start + display_value_pos_in_block
                                
                                # Skip if we already have this position in changes
                                if display_pos_abs not in queued_positions:
                                    old_display_value = display_match.group(1).lower()
                                    # Get actual length from content
                                    old_value_from_content = content[display_pos_abs:display_pos_abs + 10].lower()
                                    if 'true' in old_value_from_content:
                                        actual_old_len = 4  # 'true'
                                    elif 'false' in old_value_from_content:
                                        actual_old_len = 5  # 'false'
                                    else:
                                        actual_old_len = len(old_display_value)
                                    
                                    changes.append((display_pos_abs, display_pos_abs + actual_old_len, new_value))
                                    queued_positions.add(display_pos_abs)
                                    additional_count += 1
                                    logger.info(f"Queued additional legend display update for {chart_id}: '{old_display_value}' -> '{new_value}' at position {display_pos_abs}")
                        
                        if additional_count > 0:
                            logger.info(f"Found {additional_count} additional legend blocks to update for {chart_id}")
                    elif legend_starts:
                        # Legend exists but without display property, add it to first legend block
                        first_legend = legend_starts[0]
                        legend_block_start_rel = first_legend.end()
                        # Find closing brace of first legend block
                        legend_block_content = chart_block[legend_block_start_rel:]
                        brace_count = 1
                        legend_block_end_rel = legend_block_start_rel
                        for i, char in enumerate(legend_block_content):
                            if char == '{':
                                brace_count += 1
                            elif char == '}':
                                brace_count -= 1
                                if brace_count == 0:
                                    legend_block_end_rel = legend_block_start_rel + i
                                    break
                        
                        # Insert display property at the beginning of legend block
                        display_property = f"display: {'true' if show_legend else 'false'},\n                "
                        insert_pos = start_pos + legend_block_start_rel
                        changes.append((insert_pos, insert_pos, display_property))
                        logger.info(f"Queued legend display addition for {chart_id}: {show_legend} (added to existing block)")
                    else:
                        # Legend setting doesn't exist, try to find plugins section to add it
                        plugins_pattern = r'plugins\s*:\s*\{'
                        plugins_match = re.search(plugins_pattern, chart_block, re.DOTALL)
                        if plugins_match:
                            plugins_start = start_pos + plugins_match.end()
                            # Find closing brace of plugins section
                            plugins_block = content[plugins_start:plugins_start + 5000]
                            brace_count = 1
                            plugins_end = plugins_start
                            for i, char in enumerate(plugins_block):
                                if char == '{':
                                    brace_count += 1
                                elif char == '}':
                                    brace_count -= 1
                                    if brace_count == 0:
                                        plugins_end = plugins_start + i
                                        break
                            
                            plugins_section = content[plugins_start:plugins_end]
                            # Find a good place to insert (after title if exists)
                            title_match = re.search(r'title\s*:\s*\{[^}]*\}', plugins_section, re.DOTALL)
                            if title_match:
                                insert_pos = plugins_start + title_match.end()
                                legend_setting = f",\n            legend: {{\n                display: {'true' if show_legend else 'false'}\n            }}"
                                changes.append((insert_pos, insert_pos, legend_setting))
                                logger.info(f"Queued legend display addition for {chart_id}: {show_legend}")
                            else:
                                # Insert at the beginning of plugins section
                                legend_setting = f"\n            legend: {{\n                display: {'true' if show_legend else 'false'}\n            }},"
                                changes.append((plugins_start, plugins_start, legend_setting))
                                logger.info(f"Queued legend display addition for {chart_id}: {show_legend}")
                        else:
                            logger.warning(f"Could not find plugins section to add legend for {chart_id}")
                else:
                    logger.warning(f"Could not find context for legend update for {chart_id}")
            
            # 4. Update show_labels (datalabels display)
            if show_labels is not None:
                if ctx_match:
                    start_pos = ctx_match.end()
                    # Look for Chart initialization and find all datalabels occurrences
                    chart_block = content[start_pos:start_pos + 10000]  # Increased search range to 10000
                    
                    # Find all datalabels blocks - they can be in plugins section or as separate config
                    # Pattern 1: datalabels: { display: true/false, ... }
                    # Pattern 2: datalabels: { anchor: ..., display: true/false, ... }
                    # We need to find all occurrences and update them
                    
                    # Find all datalabels blocks with display property
                    # We need to find all occurrences of "display: true/false" that are inside datalabels blocks
                    # Strategy: Find all datalabels blocks, then find display within each
                    
                    # First, find all datalabels block starts
                    datalabels_starts = list(re.finditer(r'datalabels\s*:\s*\{', chart_block, re.IGNORECASE))
                    logger.debug(f"Found {len(datalabels_starts)} datalabels blocks in chart block for {chart_id}")
                    
                    all_datalabels_matches = []
                    for idx, datalabels_start in enumerate(datalabels_starts):
                        # Find the matching closing brace for this datalabels block
                        block_start_rel = datalabels_start.end()  # Relative to chart_block
                        block_content = chart_block[block_start_rel:]
                        brace_count = 1
                        block_end_rel = block_start_rel
                        found_end = False
                        for i, char in enumerate(block_content):
                            if char == '{':
                                brace_count += 1
                            elif char == '}':
                                brace_count -= 1
                                if brace_count == 0:
                                    block_end_rel = block_start_rel + i
                                    found_end = True
                                    break
                        
                        if not found_end:
                            logger.warning(f"Could not find closing brace for datalabels block {idx + 1} in {chart_id}")
                            continue
                        
                        # Now search for display: true/false within this block
                        block_text = chart_block[block_start_rel:block_end_rel]
                        display_match = re.search(r'display\s*:\s*(true|false)\b', block_text, re.IGNORECASE)
                        if display_match:
                            # Calculate absolute position: start_pos (chart block start) + block_start_rel + display position
                            display_pos_abs = start_pos + block_start_rel + display_match.start(1)
                            display_value = display_match.group(1).lower()  # Normalize to lowercase
                            # Create a mock match object
                            class MockMatch:
                                def __init__(self, pos, value, idx):
                                    self.start = lambda: pos
                                    self.group = lambda n: value if n == 1 else None
                                    self.index = idx
                            all_datalabels_matches.append(MockMatch(display_pos_abs, display_value, idx))
                            logger.debug(f"Found display in datalabels block {idx + 1}: {display_value} at absolute position {display_pos_abs}")
                        else:
                            logger.debug(f"Datalabels block {idx + 1} has no display property")
                    
                    if all_datalabels_matches:
                        # Update all occurrences - use a more aggressive approach to find ALL display values
                        logger.info(f"Found {len(all_datalabels_matches)} datalabels display settings to update for {chart_id}")
                        
                        # Set the target value - we want ALL datalabels display values to be this
                        new_value = 'true' if show_labels else 'false'
                        
                        # Find all datalabels blocks and update ALL display values within them
                        # Force update all found datalabels blocks to the new value, regardless of current value
                        queued_positions = set()
                        for datalabels_match in all_datalabels_matches:
                            old_value = datalabels_match.group(1)
                            logger.debug(f"Datalabels block {datalabels_match.index + 1} for {chart_id}: old_value='{old_value}', new_value='{new_value}'")
                            
                            # Always update to new_value, regardless of current value
                            absolute_pos = datalabels_match.start()  # Already includes start_pos
                            
                            # Skip if we already queued this position
                            if absolute_pos in queued_positions:
                                logger.debug(f"Skipping duplicate position {absolute_pos} for datalabels block {datalabels_match.index + 1}")
                                continue
                            
                            # Get the actual old value length from the content to handle case variations
                            old_value_from_content = content[absolute_pos:absolute_pos + 10].lower()
                            if 'true' in old_value_from_content:
                                actual_old_len = 4  # 'true'
                            elif 'false' in old_value_from_content:
                                actual_old_len = 5  # 'false'
                            else:
                                actual_old_len = len(old_value)
                            
                            changes.append((absolute_pos, absolute_pos + actual_old_len, new_value))
                            queued_positions.add(absolute_pos)
                            logger.info(f"Queued datalabels display update for {chart_id}: '{old_value}' -> '{new_value}' (datalabels block {datalabels_match.index + 1}) at position {absolute_pos}")
                        
                        # Additional pass: find ALL display: true/false patterns in datalabels blocks
                        # This ensures we catch ALL display values, regardless of current value
                        # Track positions we've already queued
                        queued_positions = {c[0] for c in changes}
                        
                        # Find all "datalabels: {" blocks and update ALL display values within them
                        all_datalabels_blocks = list(re.finditer(r'datalabels\s*:\s*\{', chart_block, re.IGNORECASE))
                        additional_count = 0
                        for datalabels_block_match in all_datalabels_blocks:
                            # Find the closing brace for this datalabels block
                            block_start = datalabels_block_match.end()
                            block_content = chart_block[block_start:]
                            brace_count = 1
                            block_end = block_start
                            found_end = False
                            for i, char in enumerate(block_content):
                                if char == '{':
                                    brace_count += 1
                                elif char == '}':
                                    brace_count -= 1
                                    if brace_count == 0:
                                        block_end = block_start + i
                                        found_end = True
                                        break
                            
                            if not found_end:
                                continue
                            
                            # Search for ANY display: true/false within this block
                            block_text = chart_block[block_start:block_end]
                            display_match = re.search(r'display\s*:\s*(true|false)\b', block_text, re.IGNORECASE)
                            if display_match:
                                # Calculate absolute position: start_pos + block_start + position of value
                                display_value_pos_in_block = display_match.start(1)
                                display_pos_abs = start_pos + block_start + display_value_pos_in_block
                                
                                # Skip if we already have this position in changes
                                if display_pos_abs not in queued_positions:
                                    old_display_value = display_match.group(1).lower()
                                    # Get actual length from content
                                    old_value_from_content = content[display_pos_abs:display_pos_abs + 10].lower()
                                    if 'true' in old_value_from_content:
                                        actual_old_len = 4  # 'true'
                                    elif 'false' in old_value_from_content:
                                        actual_old_len = 5  # 'false'
                                    else:
                                        actual_old_len = len(old_display_value)
                                    
                                    changes.append((display_pos_abs, display_pos_abs + actual_old_len, new_value))
                                    queued_positions.add(display_pos_abs)
                                    additional_count += 1
                                    logger.info(f"Queued additional datalabels display update for {chart_id}: '{old_display_value}' -> '{new_value}' at position {display_pos_abs}")
                        
                        if additional_count > 0:
                            logger.info(f"Found {additional_count} additional datalabels blocks to update for {chart_id}")
                    else:
                        # No datalabels found, try to find plugins section and add it
                        plugins_pattern = r'plugins\s*:\s*\{'
                        plugins_match = re.search(plugins_pattern, chart_block, re.DOTALL)
                        
                        if plugins_match:
                            plugins_start = start_pos + plugins_match.end()
                            # Find the closing brace of plugins section - increase search range for large sections
                            plugins_block = content[plugins_start:plugins_start + 5000]  # Increased from 1000 to 5000
                            brace_count = 1
                            plugins_end = plugins_start
                            for i, char in enumerate(plugins_block):
                                if char == '{':
                                    brace_count += 1
                                elif char == '}':
                                    brace_count -= 1
                                    if brace_count == 0:
                                        plugins_end = plugins_start + i
                                        break
                            
                            if plugins_end == plugins_start:
                                logger.warning(f"Could not find closing brace for plugins section in {chart_id} (datalabels), using extended search")
                                # Try to find the next closing brace after a reasonable distance
                                extended_search = content[plugins_start:plugins_start + 10000]
                                next_brace = extended_search.find('}')
                                if next_brace > 0:
                                    plugins_end = plugins_start + next_brace
                                else:
                                    logger.error(f"Could not find plugins section end for {chart_id} (datalabels)")
                                    continue
                            
                            plugins_section = content[plugins_start:plugins_end]
                            logger.debug(f"Found plugins section for {chart_id} (datalabels): {len(plugins_section)} characters")
                            
                            # Check if datalabels exists without display property
                            datalabels_simple_pattern = r'datalabels\s*:\s*\{'
                            simple_datalabels_match = re.search(datalabels_simple_pattern, plugins_section, re.DOTALL)
                            
                            if simple_datalabels_match:
                                # Datalabels exists but without display, add display property
                                datalabels_start = plugins_start + simple_datalabels_match.end()
                                # Find the closing brace of this datalabels block
                                datalabels_block = content[datalabels_start:plugins_end]
                                brace_count = 1
                                datalabels_end = datalabels_start
                                for i, char in enumerate(datalabels_block):
                                    if char == '{':
                                        brace_count += 1
                                    elif char == '}':
                                        brace_count -= 1
                                        if brace_count == 0:
                                            datalabels_end = datalabels_start + i
                                            break
                                
                                # Insert display property at the beginning of datalabels block
                                display_property = f"display: {'true' if show_labels else 'false'},\n                "
                                changes.append((datalabels_start, datalabels_start, display_property))
                                logger.info(f"Queued datalabels display addition for {chart_id}: {show_labels} (added to existing block)")
                            else:
                                # Datalabels doesn't exist, add it
                                # Find a good place to insert (after legend if exists, or after title)
                                legend_match = re.search(r'legend\s*:\s*\{[^}]*\}', plugins_section, re.DOTALL)
                                if legend_match:
                                    insert_pos = plugins_start + legend_match.end()
                                    # Add comma and datalabels setting
                                    datalabels_setting = f",\n            datalabels: {{\n                display: {'true' if show_labels else 'false'}\n            }}"
                                    changes.append((insert_pos, insert_pos, datalabels_setting))
                                    logger.info(f"Queued datalabels display addition for {chart_id}: {show_labels}")
                                else:
                                    # Insert after title or at the end
                                    title_match = re.search(r'title\s*:\s*\{[^}]*\}', plugins_section, re.DOTALL)
                                    if title_match:
                                        insert_pos = plugins_start + title_match.end()
                                        datalabels_setting = f",\n            datalabels: {{\n                display: {'true' if show_labels else 'false'}\n            }}"
                                        changes.append((insert_pos, insert_pos, datalabels_setting))
                                        logger.info(f"Queued datalabels display addition for {chart_id}: {show_labels}")
                                    else:
                                        # Insert at the beginning of plugins section
                                        datalabels_setting = f"\n            datalabels: {{\n                display: {'true' if show_labels else 'false'}\n            }},"
                                        changes.append((plugins_start, plugins_start, datalabels_setting))
                                        logger.info(f"Queued datalabels display addition for {chart_id}: {show_labels}")
                        else:
                            # Fallback: Search for all datalabels blocks in the entire chart_block
                            logger.warning(f"Could not find plugins section for {chart_id} datalabels, searching entire chart block")
                            # The datalabels_starts search already covers the entire chart_block, so we should have found them
                            if not all_datalabels_matches and datalabels_starts:
                                logger.warning(f"Found {len(datalabels_starts)} datalabels blocks but no display properties in {chart_id}")
                            elif not all_datalabels_matches:
                                logger.warning(f"No datalabels blocks found at all for {chart_id}")
                else:
                    logger.warning(f"Could not find context for datalabels update for {chart_id}")
            
            # 5. Update is_visible - hide/show chart container
            if is_visible is not None:
                # Find the container div that contains the canvas with this chart_id
                # Pattern: <div...>...<canvas id="chart_id"...> or <div...>...<canvas id='chart_id'...>
                # We need to find the parent div that contains this canvas
                # Use exact match to ensure chart_id is not part of another id
                escaped_chart_id = re.escape(chart_id)
                canvas_pattern = rf'<canvas[^>]*id\s*=\s*["\']{escaped_chart_id}(?![a-zA-Z0-9_])["\'][^>]*>'
                canvas_match = re.search(canvas_pattern, content, re.IGNORECASE)
                
                if canvas_match:
                    # Find the opening div tag before this canvas
                    # Look backwards from canvas position to find the containing div
                    canvas_start = canvas_match.start()
                    # Search backwards up to 500 characters to find the div
                    search_start = max(0, canvas_start - 500)
                    before_canvas = content[search_start:canvas_start]
                    
                    # Find the most recent opening div tag (could be <div>, <div class="...">, etc.)
                    # Match div with optional attributes
                    div_pattern = r'<div[^>]*>'
                    div_matches = list(re.finditer(div_pattern, before_canvas, re.IGNORECASE))
                    
                    if div_matches:
                        # Get the last (most recent) div before canvas
                        last_div = div_matches[-1]
                        div_start_relative = last_div.start()
                        div_start_absolute = search_start + div_start_relative
                        
                        # Check if div has style attribute
                        div_tag = last_div.group(0)
                        style_match = re.search(r'style\s*=\s*["\']([^"\']*)["\']', div_tag, re.IGNORECASE)
                        
                        if is_visible:
                            # Show the chart - remove display:none if present
                            if style_match:
                                style_content = style_match.group(1)
                                # Remove display:none or display: none
                                new_style = re.sub(r'display\s*:\s*none\s*;?\s*', '', style_content, flags=re.IGNORECASE)
                                new_style = re.sub(r';\s*;+', ';', new_style)  # Clean up double semicolons
                                new_style = new_style.strip('; ')
                                
                                if new_style != style_content:
                                    # Replace the style attribute
                                    old_style_attr = style_match.group(0)
                                    if new_style:
                                        new_style_attr = f'style="{new_style}"'
                                    else:
                                        # Remove style attribute if empty
                                        new_style_attr = ''
                                    
                                    # Replace in the div tag
                                    new_div_tag = div_tag.replace(old_style_attr, new_style_attr)
                                    if not new_style:
                                        # Remove empty style attribute
                                        new_div_tag = re.sub(r'\s+style\s*=\s*["\']["\']', '', new_div_tag)
                                    
                                    changes.append((div_start_absolute, div_start_absolute + len(div_tag), new_div_tag))
                                    logger.info(f"Queued visibility update for {chart_id}: showing chart")
                            else:
                                # No style attribute, chart is already visible
                                logger.debug(f"Chart {chart_id} container has no style attribute, already visible")
                        else:
                            # Hide the chart - add display:none
                            if style_match:
                                style_content = style_match.group(1)
                                # Check if display:none already exists
                                if not re.search(r'display\s*:\s*none', style_content, re.IGNORECASE):
                                    # Add display:none
                                    new_style = style_content.rstrip('; ').strip()
                                    if new_style:
                                        new_style += '; display:none'
                                    else:
                                        new_style = 'display:none'
                                    
                                    old_style_attr = style_match.group(0)
                                    new_style_attr = f'style="{new_style}"'
                                    new_div_tag = div_tag.replace(old_style_attr, new_style_attr)
                                    
                                    changes.append((div_start_absolute, div_start_absolute + len(div_tag), new_div_tag))
                                    logger.info(f"Queued visibility update for {chart_id}: hiding chart")
                            else:
                                # Add style attribute with display:none
                                # Find the closing > of the div tag
                                div_end_in_tag = div_tag.rfind('>')
                                if div_end_in_tag > 0:
                                    new_div_tag = div_tag[:div_end_in_tag] + ' style="display:none"' + div_tag[div_end_in_tag:]
                                    changes.append((div_start_absolute, div_start_absolute + len(div_tag), new_div_tag))
                                    logger.info(f"Queued visibility update for {chart_id}: hiding chart (added style)")
                else:
                    logger.warning(f"Could not find canvas element for chart {chart_id} to update visibility")
            
            # 6. Update color_palette - replace backgroundColor array
            if color_palette:
                palette = get_color_palette(color_palette)
                palette_colors = palette['colors']
                
                if ctx_match:
                    start_pos = ctx_match.end()
                    chart_block = content[start_pos:start_pos + 10000]
                    
                    # Find backgroundColor array - handle both single-line and multi-line
                    # Look for backgroundColor: [ ... ] pattern
                    bg_color_pattern = r'backgroundColor\s*:\s*\['
                    bg_matches = list(re.finditer(bg_color_pattern, chart_block, re.IGNORECASE))
                    
                    for bg_match in bg_matches:
                        # Find the matching closing bracket
                        bg_start_rel = bg_match.end()  # Position after "backgroundColor: ["
                        bg_content = chart_block[bg_start_rel:]
                        bracket_count = 1
                        bg_end_rel = bg_start_rel
                        found_end = False
                        
                        for i, char in enumerate(bg_content):
                            if char == '[':
                                bracket_count += 1
                            elif char == ']':
                                bracket_count -= 1
                                if bracket_count == 0:
                                    bg_end_rel = bg_start_rel + i + 1  # Include closing bracket
                                    found_end = True
                                    break
                        
                        if found_end:
                            # Calculate absolute positions
                            bg_start_abs = start_pos + bg_match.start()
                            bg_end_abs = start_pos + bg_end_rel
                            
                            # Get the original content to preserve indentation
                            original_bg = chart_block[bg_match.start():bg_end_rel]
                            
                            # Determine indentation from original (look for newline after ":")
                            indent_match = re.search(r':\s*(\n\s*)', original_bg)
                            if indent_match:
                                indent = indent_match.group(1)  # e.g., "\n                    "
                                # Use same indentation for colors
                                colors_str = (',' + indent).join([f"'{color}'" for color in palette_colors])
                                new_bg_array = f"backgroundColor: [{indent}{colors_str}{indent}]"
                            else:
                                # Single line format
                                colors_str = ', '.join([f"'{color}'" for color in palette_colors])
                                new_bg_array = f"backgroundColor: [{colors_str}]"
                            
                            # Check if this position is already in changes
                            if not any(c[0] == bg_start_abs for c in changes):
                                changes.append((bg_start_abs, bg_end_abs, new_bg_array))
                                logger.info(f"Queued color_palette update for {chart_id}: palette={color_palette} ({len(palette_colors)} colors) at position {bg_start_abs}")
                            break  # Only update first occurrence per chart
            
            # 7. Update allow_export - conditionally show/hide export buttons
            if allow_export is not None:
                # Find the export button code (addChartExportButtons call) for this chart
                # Pattern: addChartExportButtons('chart_id', ...) or addChartExportButtons("chart_id", ...)
                export_pattern = rf'addChartExportButtons\s*\(\s*["\']{re.escape(chart_id)}["\']'
                export_match = re.search(export_pattern, content, re.IGNORECASE)
                
                if export_match:
                    # Find the entire setTimeout block that contains this export button call
                    # Look backwards to find setTimeout( and forwards to find });
                    export_start = export_match.start()
                    
                    # Find the start of setTimeout block (look backwards up to 200 chars)
                    search_start = max(0, export_start - 200)
                    before_export = content[search_start:export_start]
                    setTimeout_match = re.search(r'setTimeout\s*\(', before_export, re.IGNORECASE)
                    
                    if setTimeout_match:
                        setTimeout_start = search_start + setTimeout_match.start()
                        
                        # Find the end of setTimeout block (look forwards from export_start)
                        search_end = min(len(content), export_start + 500)
                        after_export = content[export_start:search_end]
                        closing_match = re.search(r'}\s*\)\s*;', after_export)
                        
                        if closing_match:
                            setTimeout_end = export_start + closing_match.end()
                            setTimeout_block = content[setTimeout_start:setTimeout_end]
                            
                            if allow_export:
                                # Show export buttons - ensure the setTimeout block exists
                                # Check if it's already commented out
                                if '//' in setTimeout_block.split('\n')[0].strip()[:2]:
                                    # Uncomment the block
                                    uncommented = re.sub(r'^\s*//\s*', '', setTimeout_block, flags=re.MULTILINE)
                                    changes.append((setTimeout_start, setTimeout_end, uncommented))
                                    logger.info(f"Queued export button update for {chart_id}: showing export")
                                else:
                                    # Already uncommented
                                    logger.debug(f"Export buttons for {chart_id} already enabled")
                            else:
                                # Hide export buttons - comment out the setTimeout block
                                if not '//' in setTimeout_block.split('\n')[0].strip()[:2]:
                                    # Comment each line
                                    commented_lines = []
                                    for line in setTimeout_block.split('\n'):
                                        if line.strip() and not line.strip().startswith('//'):
                                            commented_lines.append('    // ' + line.lstrip())
                                        else:
                                            commented_lines.append(line)
                                    commented_block = '\n'.join(commented_lines)
                                    changes.append((setTimeout_start, setTimeout_end, commented_block))
                                    logger.info(f"Queued export button update for {chart_id}: hiding export")
                                else:
                                    # Already commented
                                    logger.debug(f"Export buttons for {chart_id} already disabled")
                        else:
                            logger.warning(f"Could not find closing of setTimeout block for {chart_id}")
                    else:
                        # Export button might be called directly, try to comment it out
                        # Find the line with addChartExportButtons
                        line_start = content.rfind('\n', 0, export_start) + 1
                        line_end = content.find('\n', export_start)
                        if line_end == -1:
                            line_end = len(content)
                        
                        export_line = content[line_start:line_end]
                        if allow_export:
                            # Uncomment if commented
                            if export_line.strip().startswith('//'):
                                uncommented = export_line.replace('//', '', 1).lstrip()
                                changes.append((line_start, line_end, uncommented))
                                logger.info(f"Queued export button update for {chart_id}: showing export (direct call)")
                        else:
                            # Comment if not commented
                            if not export_line.strip().startswith('//'):
                                commented = '    // ' + export_line.lstrip()
                                changes.append((line_start, line_end, commented))
                                logger.info(f"Queued export button update for {chart_id}: hiding export (direct call)")
                else:
                    logger.warning(f"Could not find export button code for chart {chart_id}")
        
        # Apply all changes from end to start to preserve positions
        if changes:
            # Remove duplicate changes at the same position (keep the last one since we sort descending)
            # Group by position and keep only one change per position
            unique_changes = {}
            for start_pos, end_pos, new_text in changes:
                # Use position as key - if same position, keep the last one (will be applied first due to reverse sort)
                key = (start_pos, end_pos)
                if key not in unique_changes:
                    unique_changes[key] = (start_pos, end_pos, new_text)
                else:
                    # If same position but different text, log warning and keep the new one
                    old_text = unique_changes[key][2]
                    if old_text != new_text:
                        logger.warning(f"Duplicate change at position {start_pos}-{end_pos}: keeping '{new_text}' over '{old_text}'")
                    unique_changes[key] = (start_pos, end_pos, new_text)
            
            # Convert back to list and sort by position (descending) so we apply from end to start
            changes = list(unique_changes.values())
            changes.sort(key=lambda x: x[0], reverse=True)
            
            logger.info(f"Applying {len(changes)} unique changes to HTML file (from end to start to preserve positions)")
            applied_count = 0
            skipped_count = 0
            for start_pos, end_pos, new_text in changes:
                try:
                    # Validate positions
                    if start_pos < 0 or end_pos > len(content) or start_pos > end_pos:
                        logger.error(f"✗ Invalid position range: {start_pos}-{end_pos} (content length: {len(content)})")
                        continue
                    
                    # Get the current content at this position
                    old_content = content[start_pos:end_pos]
                    
                    # Normalize for comparison (handle whitespace differences)
                    old_normalized = old_content.strip().lower()
                    new_normalized = new_text.strip().lower()
                    
                    # Only apply if content is different
                    if old_normalized != new_normalized:
                        # Apply the change
                        content = content[:start_pos] + new_text + content[end_pos:]
                        applied_count += 1
                        logger.info(f"✓ Applied change {applied_count}/{len(changes)} at position {start_pos}-{end_pos}: '{old_content[:30].replace(chr(10), ' ').replace(chr(13), ' ')}...' -> '{new_text[:30].replace(chr(10), ' ').replace(chr(13), ' ')}...'")
                    else:
                        skipped_count += 1
                        logger.debug(f"⊘ Skipped change {skipped_count} at position {start_pos}-{end_pos}: content already matches '{new_text[:30].replace(chr(10), ' ').replace(chr(13), ' ')}...'")
                except Exception as change_error:
                    logger.error(f"✗ Error applying change at position {start_pos}-{end_pos}: {change_error}", exc_info=True)
            
            logger.info(f"Successfully applied {applied_count}/{len(changes)} changes to HTML ({skipped_count} skipped - already correct)")
        else:
            logger.info("No changes to apply to HTML file")
        
        # 5. Update display_order by reordering chart divs in HTML
        # NOTE: HTML reordering is DISABLED to prevent duplication issues
        # The display_order is saved in the database and used for:
        # - Admin panel visual editor display order (drag & drop)
        # - Future: Template rendering can use display_order to render charts in correct order
        #
        # Reordering HTML divs programmatically is error-prone and can cause:
        # - Duplication of chart divs
        # - Breaking HTML structure
        # - Loss of comments or other content
        #
        # For now, we rely on:
        # 1. Database display_order for admin panel ordering
        # 2. Manual HTML editing if order needs to change in template
        # 3. Future: Template-level ordering using display_order from database
        #
        # The display_order is still saved to the database and will be used when rendering
        # charts in the admin panel and potentially in user-facing dashboards.
        logger.debug("Skipping HTML reordering - display_order saved in database only")
        
        # Only write if content changed
        if content != original_content:
            try:
                # Write updated content back to file
                with open(template_path, 'w', encoding='utf-8') as f:
                    f.write(content)
                
                # Verify file was written correctly
                with open(template_path, 'r', encoding='utf-8') as f:
                    verify_content = f.read()
                if verify_content == content:
                    logger.info(f"✓ Successfully wrote {len(content)} characters to {template_path.name}")
                    logger.info(f"✓ File verification passed")
                else:
                    logger.error(f"✗ File verification failed - content mismatch!")
                
                logger.info(f"✓ Successfully applied {len(changes)} chart configurations to {template_path.name}")
                return True
            except Exception as write_error:
                logger.error(f"✗ Error writing to HTML file: {write_error}", exc_info=True)
                return False
        else:
            logger.info(f"✓ No changes needed for {template_path.name} (content unchanged)")
            return True
        
    except Exception as e:
        logger.error(f"Error applying chart configs to HTML: {e}", exc_info=True)
        return False

# Error handler for admin blueprint - handles errors before app-level handler
@admin_bp.errorhandler(500)
def admin_500_error(e):
    """Handle 500 errors in admin routes - return HTML, not JSON"""
    import traceback
    error_traceback = traceback.format_exc()
    logger.error(f"Admin 500 Error in {request.path}: {e}")
    logger.error(f"Traceback: {error_traceback}")
    
    # For template edit pages, return HTML error page
    if request.path.startswith('/admin/dashboards/templates/'):
        path_parts = request.path.split('/')
        if len(path_parts) >= 5:
            template_name = path_parts[4]
            if template_name.endswith('.html') and request.method == 'GET':
                error_html = f"""<!DOCTYPE html>
<html dir="rtl" lang="fa">
<head>
    <meta charset="utf-8">
    <title>خطا در ویرایش تمپلیت</title>
    <style>
        body {{ font-family: Tahoma, Arial; padding: 20px; background: #f5f5f5; }}
        .error-box {{ background: white; padding: 20px; border-radius: 5px; box-shadow: 0 2px 5px rgba(0,0,0,0.1); }}
        h1 {{ color: #d32f2f; }}
        pre {{ background: #f5f5f5; padding: 10px; border-radius: 3px; overflow-x: auto; font-size: 12px; }}
    </style>
</head>
<body>
    <div class="error-box">
        <h1>خطا در نمایش صفحه ویرایش</h1>
        <p><strong>تمپلیت:</strong> {template_name}</p>
        <p><strong>خطا:</strong> {str(e)}</p>
        <details>
            <summary>جزئیات خطا (برای توسعه‌دهندگان)</summary>
            <pre>{error_traceback}</pre>
        </details>
        <p><a href="/admin/dashboards/templates">بازگشت به لیست تمپلیت‌ها</a></p>
    </div>
</body>
</html>"""
                return Response(error_html, status=500, mimetype='text/html; charset=utf-8')
    
    # For other admin routes, return HTML error page
    error_html = f"""<!DOCTYPE html>
<html dir="rtl" lang="fa">
<head>
    <meta charset="utf-8">
    <title>خطای سرور</title>
    <style>
        body {{ font-family: Tahoma, Arial; padding: 20px; background: #f5f5f5; }}
        .error-box {{ background: white; padding: 20px; border-radius: 5px; box-shadow: 0 2px 5px rgba(0,0,0,0.1); }}
        h1 {{ color: #d32f2f; }}
        pre {{ background: #f5f5f5; padding: 10px; border-radius: 3px; overflow-x: auto; font-size: 12px; }}
    </style>
</head>
<body>
    <div class="error-box">
        <h1>خطای داخلی سرور</h1>
        <p><strong>خطا:</strong> {str(e)}</p>
        <details>
            <summary>جزئیات خطا (برای توسعه‌دهندگان)</summary>
            <pre>{error_traceback}</pre>
        </details>
        <p><a href="/admin">بازگشت به پنل مدیریت</a></p>
    </div>
</body>
</html>"""
    return Response(error_html, status=500, mimetype='text/html; charset=utf-8')


@admin_bp.route('/')
@login_required
@admin_required
def index():
    """Admin panel dashboard"""
    try:
        log_action('view_admin_panel')
    except Exception as e:
        logger.error(f"Error logging action: {e}")
    
    try:
        # Get statistics
        stats = {
            'total_users': User.query.count(),
            'total_dashboards': len(DashboardRegistry.list_all()),
            'total_access_logs': AccessLog.query.count(),
            'active_data_syncs': DataSync.query.filter_by(auto_sync_enabled=True).count(),
        }
        
        # Recent access logs
        recent_logs = AccessLog.query.order_by(AccessLog.created_at.desc()).limit(10).all()
        
        # Data sync status
        data_syncs = DataSync.query.all()
        
        return render_template('admin/index.html', 
                             stats=stats, 
                             recent_logs=recent_logs,
                             data_syncs=data_syncs)
    except Exception as e:
        logger.error(f"Error in admin index: {e}", exc_info=True)
        flash(f'خطا در بارگذاری پنل مدیریت: {str(e)}', 'error')
        return render_template('admin/index.html', 
                             stats={'total_users': 0, 'total_dashboards': 0, 'total_access_logs': 0, 'active_data_syncs': 0}, 
                             recent_logs=[],
                             data_syncs=[])


# ==================== Microservices Monitoring ====================

@admin_bp.route('/microservices')
@login_required
@admin_required
def microservices_list():
    """List all microservices and their status"""
    log_action('view_microservices')
    
    services_status = {}
    for service_name, service_info in MICROSERVICES.items():
        health_status = check_service_health(service_name)
        container_status = check_docker_container_status(service_info['container'])
        
        services_status[service_name] = {
            **service_info,
            'health': health_status,
            'container': container_status
        }
    
    return render_template('admin/microservices/list.html', services=services_status)


@admin_bp.route('/microservices/status')
@login_required
@admin_required
def microservices_status():
    """API endpoint to get all microservices status"""
    try:
        services_status = {}
        for service_name, service_info in MICROSERVICES.items():
            health_status = check_service_health(service_name)
            container_status = check_docker_container_status(service_info['container'])
            
            services_status[service_name] = {
                **service_info,
                'health': health_status,
                'container': container_status
            }
        
        return jsonify({
            'success': True,
            'services': services_status,
            'timestamp': datetime.utcnow().isoformat()
        })
    except Exception as e:
        logger.error(f"Error getting microservices status: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@admin_bp.route('/microservices/<service_name>/restart', methods=['POST'])
@login_required
@admin_required
def microservice_restart(service_name):
    """Restart a microservice"""
    if service_name not in MICROSERVICES:
        return jsonify({
            'success': False,
            'error': f'Service {service_name} not found'
        }), 404
    
    try:
        # Try to log action (non-critical, don't fail if it errors)
        try:
            log_action('restart_microservice', 'microservice', service_name)
        except Exception as log_err:
            logger.warning(f"Error logging restart action for {service_name}: {log_err}")
        
        # Attempt to restart the service
        result = restart_service(service_name)
        
        if result['success']:
            # Try to flash message (non-critical, but don't fail if it errors)
            try:
                flash(f'سرویس {MICROSERVICES[service_name]["name"]} با موفقیت راه‌اندازی مجدد شد.', 'success')
            except Exception as flash_err:
                logger.warning(f"Error flashing success message: {flash_err}")
            return jsonify(result)
        else:
            # Try to flash error message (non-critical, but don't fail if it errors)
            try:
                flash(f'خطا در راه‌اندازی مجدد سرویس: {result.get("error", "خطای نامشخص")}', 'error')
            except Exception as flash_err:
                logger.warning(f"Error flashing error message: {flash_err}")
            return jsonify(result), 500
    except Exception as e:
        logger.error(f"Error restarting microservice {service_name}: {e}", exc_info=True)
        import traceback
        error_traceback = traceback.format_exc()
        logger.error(f"Full traceback: {error_traceback}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@admin_bp.route('/microservices/<service_name>/status')
@login_required
@admin_required
def microservice_status(service_name):
    """Get status of a specific microservice"""
    if service_name not in MICROSERVICES:
        return jsonify({
            'success': False,
            'error': f'Service {service_name} not found'
        }), 404
    
    try:
        service_info = MICROSERVICES[service_name]
        health_status = check_service_health(service_name)
        container_status = check_docker_container_status(service_info['container'])
        
        return jsonify({
            'success': True,
            'service': {
                **service_info,
                'health': health_status,
                'container': container_status
            },
            'timestamp': datetime.utcnow().isoformat()
        })
    except Exception as e:
        logger.error(f"Error getting microservice status: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


# ==================== User Management ====================

@admin_bp.route('/users')
@login_required
@admin_required
def users_list():
    """List all users"""
    log_action('view_users_list')
    
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    search = request.args.get('search', '')
    
    query = User.query
    
    if search:
        query = query.filter(
            or_(
                User.name.contains(search),
                User.sso_id.contains(search),
                User.email.contains(search)
            )
        )
    
    users = query.paginate(page=page, per_page=per_page, error_out=False)
    
    return render_template('admin/users/list.html', users=users, search=search)


@admin_bp.route('/users/<int:user_id>')
@login_required
@admin_required
def user_detail(user_id):
    """View user details"""
    user = User.query.get_or_404(user_id)
    log_action('view_user', 'user', user_id)
    
    # Get user's dashboard accesses
    dashboard_accesses = DashboardAccess.query.filter_by(user_id=user_id).all()
    
    # Get user's recent access logs
    recent_logs = AccessLog.query.filter_by(user_id=user_id)\
        .order_by(AccessLog.created_at.desc()).limit(20).all()
    
    # Get organizational context
    org_context = get_user_org_context(user)
    
    return render_template('admin/users/detail.html', 
                         user=user, 
                         dashboard_accesses=dashboard_accesses,
                         recent_logs=recent_logs,
                         org_context=org_context)


@admin_bp.route('/users/<int:user_id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def user_edit(user_id):
    """Edit user"""
    user = User.query.get_or_404(user_id)
    # Get all user types for the form
    user_types = UserType.query.order_by(UserType.name).all()
    
    if request.method == 'POST':
        # Update user fields
        user.name = request.form.get('name', user.name)
        user.email = request.form.get('email', user.email)
        user.province_code = request.form.get('province_code', type=int) or None
        user.university_code = request.form.get('university_code', type=int) or None
        user.faculty_code = request.form.get('faculty_code', type=int) or None
        user.mobile_phone = request.form.get('mobile_phone') or None
        user.work_phone = request.form.get('work_phone') or None
        user.home_phone = request.form.get('home_phone') or None
        user.work_extension = request.form.get('work_extension') or None
        
        # Update access levels
        access_levels = request.form.getlist('access_levels')
        # Remove existing access levels
        user.access_levels = []
        # Add new access levels
        for level in access_levels:
            if level:
                access = AccessLevelModel(level=level, user_id=user.id)
                db.session.add(access)
        
        # Update user types
        user_type_ids = request.form.getlist('user_types')
        user.user_types = []
        for user_type_id in user_type_ids:
            if user_type_id:
                user_type = UserType.query.get(int(user_type_id))
                if user_type:
                    user.user_types.append(user_type)
        
        db.session.commit()
        log_action('modify_user', 'user', user_id, {'changes': request.form.to_dict()})
        flash('کاربر با موفقیت به‌روزرسانی شد', 'success')
        return redirect(url_for('admin.user_detail', user_id=user_id))
    
    return render_template('admin/users/edit.html', user=user, user_types=user_types)


@admin_bp.route('/users/new', methods=['GET', 'POST'])
@login_required
@admin_required
def user_create():
    """Create new user"""
    # Get all user types for the form
    user_types = UserType.query.order_by(UserType.name).all()
    
    if request.method == 'POST':
        sso_id = request.form.get('sso_id')
        if User.query.filter_by(sso_id=sso_id).first():
            flash('کاربری با این SSO ID وجود دارد', 'error')
            return render_template('admin/users/create.html', user_types=user_types)
        
        user = User(
            sso_id=sso_id,
            name=request.form.get('name'),
            email=request.form.get('email'),
            province_code=request.form.get('province_code', type=int) or None,
            university_code=request.form.get('university_code', type=int) or None,
            faculty_code=request.form.get('faculty_code', type=int) or None,
            mobile_phone=request.form.get('mobile_phone') or None,
            work_phone=request.form.get('work_phone') or None,
            home_phone=request.form.get('home_phone') or None,
            work_extension=request.form.get('work_extension') or None,
        )
        db.session.add(user)
        db.session.flush()
        
        # Add access levels
        access_levels = request.form.getlist('access_levels')
        for level in access_levels:
            if level:
                access = AccessLevelModel(level=level, user_id=user.id)
                db.session.add(access)
        
        # Add user types
        user_type_ids = request.form.getlist('user_types')
        for user_type_id in user_type_ids:
            if user_type_id:
                user_type = UserType.query.get(int(user_type_id))
                if user_type:
                    user.user_types.append(user_type)
        
        db.session.commit()
        log_action('create_user', 'user', user.id)
        flash('کاربر با موفقیت ایجاد شد', 'success')
        return redirect(url_for('admin.user_detail', user_id=user.id))
    
    return render_template('admin/users/create.html', user_types=user_types)


# ==================== User Types Management ====================

@admin_bp.route('/user-types')
@login_required
@admin_required
def user_types_list():
    """List all user types"""
    user_types = UserType.query.order_by(UserType.name).all()
    log_action('view_user_types_list')
    return render_template('admin/user_types/list.html', user_types=user_types)


@admin_bp.route('/user-types/new', methods=['GET', 'POST'])
@login_required
@admin_required
def user_type_create():
    """Create new user type"""
    if request.method == 'POST':
        name = request.form.get('name')
        description = request.form.get('description') or None
        
        # Check if user type with this name already exists
        if UserType.query.filter_by(name=name).first():
            flash('نوع کاربری با این نام قبلاً تعریف شده است', 'error')
            return render_template('admin/user_types/create.html')
        
        user_type = UserType(
            name=name,
            description=description
        )
        db.session.add(user_type)
        db.session.commit()
        log_action('create_user_type', 'user_type', user_type.id)
        flash('نوع کاربری با موفقیت ایجاد شد', 'success')
        return redirect(url_for('admin.user_types_list'))
    
    return render_template('admin/user_types/create.html')


@admin_bp.route('/user-types/<int:user_type_id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def user_type_edit(user_type_id):
    """Edit user type"""
    user_type = UserType.query.get_or_404(user_type_id)
    
    if request.method == 'POST':
        name = request.form.get('name')
        description = request.form.get('description') or None
        
        # Check if another user type with this name exists
        existing = UserType.query.filter_by(name=name).first()
        if existing and existing.id != user_type_id:
            flash('نوع کاربری با این نام قبلاً تعریف شده است', 'error')
            return render_template('admin/user_types/edit.html', user_type=user_type)
        
        user_type.name = name
        user_type.description = description
        user_type.updated_at = datetime.utcnow()
        
        db.session.commit()
        log_action('modify_user_type', 'user_type', user_type_id, {'changes': request.form.to_dict()})
        flash('نوع کاربری با موفقیت به‌روزرسانی شد', 'success')
        return redirect(url_for('admin.user_types_list'))
    
    return render_template('admin/user_types/edit.html', user_type=user_type)


@admin_bp.route('/user-types/<int:user_type_id>/delete', methods=['POST'])
@login_required
@admin_required
def user_type_delete(user_type_id):
    """Delete user type"""
    user_type = UserType.query.get_or_404(user_type_id)
    
    # Check if any users have this type
    if user_type.users:
        flash(f'نمی‌توان این نوع کاربری را حذف کرد زیرا {len(user_type.users)} کاربر از آن استفاده می‌کنند', 'error')
        return redirect(url_for('admin.user_types_list'))
    
    db.session.delete(user_type)
    db.session.commit()
    log_action('delete_user_type', 'user_type', user_type_id)
    flash('نوع کاربری با موفقیت حذف شد', 'success')
    return redirect(url_for('admin.user_types_list'))


# ==================== Knowledge Management ====================

@admin_bp.route('/knowledge/articles')
@login_required
@admin_required
def knowledge_articles_list():
    """List all knowledge articles with filtering and search"""
    log_action('view_knowledge_articles_list')
    
    # Get filter parameters
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    search = request.args.get('search', '')
    status = request.args.get('status', '')
    category_id = request.args.get('category_id', type=int)
    date_from = request.args.get('date_from', '')
    date_to = request.args.get('date_to', '')
    author_type = request.args.get('author_type', '')  # Filter by user type
    
    # Get categories for filter dropdown
    try:
        categories_response = requests.get(
            f"{os.getenv('KNOWLEDGE_SERVICE_URL', 'http://localhost:5008')}/api/knowledge/categories",
            timeout=5
        )
        categories = categories_response.json().get('categories', []) if categories_response.ok else []
    except Exception as e:
        logger.warning(f"Error fetching categories: {e}")
        categories = []
    
    # Get user types for filtering by "مسئول مدیریت دانش"
    knowledge_manager_type_id = None
    try:
        user_types = UserType.query.filter_by(name='مسئول مدیریت دانش').all()
        knowledge_manager_type_id = user_types[0].id if user_types else None
    except Exception as e:
        logger.warning(f"Error fetching user types: {e}")
        knowledge_manager_type_id = None
    
    # Get all users for author lookup
    all_users = {}
    try:
        users = User.query.all()
        all_users = {u.id: u for u in users}
    except Exception as e:
        logger.error(f"Error fetching users: {e}", exc_info=True)
        all_users = {}
    
    # Build API request
    api_url = f"{os.getenv('KNOWLEDGE_SERVICE_URL', 'http://localhost:5008')}/api/knowledge/articles"
    params = {
        'page': page,
        'per_page': per_page,
    }
    
    if search:
        params['search'] = search
    if status:
        params['status'] = status
    else:
        params['status'] = ''  # Get all statuses for admin
    if category_id:
        params['category_id'] = category_id
    if date_from:
        params['date_from'] = date_from
    if date_to:
        params['date_to'] = date_to
    
    try:
        # Get token for API request
        token = get_access_token_from_session()
        headers = {'X-Admin-Request': 'true'}  # Flag for admin requests
        if token:
            headers['Authorization'] = f'Bearer {token}'
            headers['X-Auth-Token'] = token
        
        response = requests.get(api_url, params=params, headers=headers, timeout=10)
        
        if response.ok:
            data = response.json()
            articles = data.get('articles', [])
            
            # Filter by author type if specified
            if author_type == 'knowledge_manager' and knowledge_manager_type_id:
                # Get all users with this type
                knowledge_managers = User.query.join(User.user_types).filter(
                    UserType.id == knowledge_manager_type_id
                ).all()
                manager_ids = [u.id for u in knowledge_managers]
                articles = [a for a in articles if a.get('author_id') in manager_ids]
            
            total = len(articles) if author_type else data.get('total', 0)
            pages = (total + per_page - 1) // per_page if total else 1
            
            return render_template('admin/knowledge/articles/list.html',
                                 articles=articles,
                                 categories=categories,
                                 all_users=all_users,
                                 page=page,
                                 pages=pages,
                                 total=total,
                                 per_page=per_page,
                                 search=search,
                                 status=status,
                                 category_id=category_id,
                                 date_from=date_from,
                                 date_to=date_to,
                                 author_type=author_type)
        else:
            flash('خطا در دریافت مقالات', 'error')
            return render_template('admin/knowledge/articles/list.html',
                                 articles=[],
                                 categories=categories,
                                 all_users={},
                                 page=1,
                                 pages=1,
                                 total=0,
                                 per_page=per_page,
                                 search=search,
                                 status=status,
                                 category_id=category_id,
                                 date_from=date_from,
                                 date_to=date_to,
                                 author_type=author_type)
    except Exception as e:
        logger.error(f"Error fetching articles: {e}", exc_info=True)
        flash(f'خطا در ارتباط با سرویس مدیریت دانش: {str(e)}', 'error')
        return render_template('admin/knowledge/articles/list.html',
                             articles=[],
                             categories=[],
                             all_users={},
                             page=1,
                             pages=1,
                             total=0,
                             per_page=per_page,
                             search=search,
                             status=status,
                             category_id=category_id,
                             date_from=date_from,
                             date_to=date_to,
                             author_type=author_type)


@admin_bp.route('/knowledge/articles/<int:article_id>')
@login_required
@admin_required
def knowledge_article_detail(article_id):
    """View article details"""
    log_action('view_knowledge_article', 'article', article_id)
    
    try:
        api_url = f"{os.getenv('KNOWLEDGE_SERVICE_URL', 'http://localhost:5008')}/api/knowledge/articles/{article_id}"
        token = get_access_token_from_session()
        headers = {'X-Admin-Request': 'true'}  # Flag for admin requests
        if token:
            headers['Authorization'] = f'Bearer {token}'
            headers['X-Auth-Token'] = token
        
        response = requests.get(api_url, headers=headers, timeout=10)
        
        if response.ok:
            article = response.json()
            # Get author info
            author = User.query.get(article.get('author_id'))
            return render_template('admin/knowledge/articles/detail.html', article=article, author=author)
        else:
            flash('مقاله یافت نشد', 'error')
            return redirect(url_for('admin.knowledge_articles_list'))
    except Exception as e:
        logger.error(f"Error fetching article: {e}", exc_info=True)
        flash(f'خطا در دریافت مقاله: {str(e)}', 'error')
        return redirect(url_for('admin.knowledge_articles_list'))


@admin_bp.route('/knowledge/articles/new', methods=['GET', 'POST'])
@login_required
@admin_required
def knowledge_article_create():
    """Create new article"""
    if request.method == 'POST':
        try:
            api_url = f"{os.getenv('KNOWLEDGE_SERVICE_URL', 'http://localhost:5008')}/api/knowledge/articles"
            token = get_access_token_from_session()
            
            if not token:
                flash('توکن احراز هویت یافت نشد. لطفاً مجدداً وارد سیستم شوید.', 'error')
                return redirect(url_for('admin.knowledge_articles_list'))
            
            headers = {'Content-Type': 'application/json', 'X-Admin-Request': 'true'}  # Flag for admin requests
            headers['Authorization'] = f'Bearer {token}'
            headers['X-Auth-Token'] = token
            
            logger.info(f"Creating article - token present: {bool(token)}, token length: {len(token) if token else 0}")
            
            data = {
                'title': request.form.get('title'),
                'content': request.form.get('content'),
                'summary': request.form.get('summary'),
                'category_id': request.form.get('category_id', type=int) or None,
                'status': request.form.get('status', 'draft'),
                'tags': [t.strip() for t in request.form.get('tags', '').split(',') if t.strip()],
                'publish_start_date': request.form.get('publish_start_date') or None,
                'publish_end_date': request.form.get('publish_end_date') or None,
                'allowed_user_types': [int(ut_id) for ut_id in request.form.getlist('allowed_user_types') if ut_id]
            }
            
            # Get current user ID
            user_id = current_user.id if current_user.is_authenticated else None
            if not user_id:
                flash('کاربر احراز هویت نشده است', 'error')
                return redirect(url_for('admin.knowledge_articles_list'))
            
            data['author_id'] = user_id
            
            response = requests.post(api_url, json=data, headers=headers, timeout=10)
            
            if response.ok:
                article = response.json()
                article_id = article.get('id')
                log_action('create_knowledge_article', 'article', article_id)
                
                # Handle file uploads if any (files will be uploaded via AJAX in the frontend)
                # The frontend will handle file uploads after article creation
                
                flash('مقاله با موفقیت ایجاد شد', 'success')
                return redirect(url_for('admin.knowledge_article_detail', article_id=article_id))
            else:
                error_data = {}
                try:
                    if response.content:
                        error_data = response.json()
                except:
                    error_data = {'message': response.text or 'خطای نامشخص'}
                
                error_msg = error_data.get("message", error_data.get("error", "خطای نامشخص"))
                logger.error(f"Error creating article: {response.status_code} - {error_msg}")
                flash(f'خطا در ایجاد مقاله: {error_msg}', 'error')
        except Exception as e:
            logger.error(f"Error creating article: {e}", exc_info=True)
            flash(f'خطا در ایجاد مقاله: {str(e)}', 'error')
    
    # GET request - show form
    try:
        categories_response = requests.get(
            f"{os.getenv('KNOWLEDGE_SERVICE_URL', 'http://localhost:5008')}/api/knowledge/categories",
            timeout=5
        )
        categories = categories_response.json().get('categories', []) if categories_response.ok else []
    except:
        categories = []
    
    # Get user types for access control
    user_types = UserType.query.order_by(UserType.name).all()
    
    return render_template('admin/knowledge/articles/create.html', categories=categories, user_types=user_types)


@admin_bp.route('/knowledge/articles/<int:article_id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def knowledge_article_edit(article_id):
    """Edit article"""
    try:
        api_url = f"{os.getenv('KNOWLEDGE_SERVICE_URL', 'http://localhost:5008')}/api/knowledge/articles/{article_id}"
        token = get_access_token_from_session()
        headers = {'X-Admin-Request': 'true'}  # Flag for admin requests
        if token:
            headers['Authorization'] = f'Bearer {token}'
            headers['X-Auth-Token'] = token
        
        if request.method == 'POST':
            headers['Content-Type'] = 'application/json'
            data = {
                'title': request.form.get('title'),
                'content': request.form.get('content'),
                'summary': request.form.get('summary'),
                'category_id': request.form.get('category_id', type=int) or None,
                'status': request.form.get('status', 'draft'),
                'tags': [t.strip() for t in request.form.get('tags', '').split(',') if t.strip()],
                'publish_start_date': request.form.get('publish_start_date') or None,
                'publish_end_date': request.form.get('publish_end_date') or None,
                'allowed_user_types': [int(ut_id) for ut_id in request.form.getlist('allowed_user_types') if ut_id]
            }
            
            response = requests.put(api_url, json=data, headers=headers, timeout=10)
            
            if response.ok:
                log_action('modify_knowledge_article', 'article', article_id)
                flash('مقاله با موفقیت به‌روزرسانی شد', 'success')
                return redirect(url_for('admin.knowledge_article_detail', article_id=article_id))
            else:
                error_data = response.json() if response.content else {}
                flash(f'خطا در به‌روزرسانی مقاله: {error_data.get("message", "خطای نامشخص")}', 'error')
        
        # GET request - fetch article
        response = requests.get(api_url, headers=headers, timeout=10)
        
        if response.ok:
            article = response.json()
            
            # Convert Gregorian dates to Jalali for display
            if article.get('publish_start_date'):
                try:
                    from datetime import datetime as dt
                    gdate = dt.fromisoformat(article['publish_start_date'].replace('Z', '+00:00'))
                    jdate = jdatetime.datetime.fromgregorian(datetime=gdate)
                    article['publish_start_date'] = jdate.strftime('%Y/%m/%d')
                except:
                    article['publish_start_date'] = None
            
            if article.get('publish_end_date'):
                try:
                    from datetime import datetime as dt
                    gdate = dt.fromisoformat(article['publish_end_date'].replace('Z', '+00:00'))
                    jdate = jdatetime.datetime.fromgregorian(datetime=gdate)
                    article['publish_end_date'] = jdate.strftime('%Y/%m/%d')
                except:
                    article['publish_end_date'] = None
            
            # Get categories
            try:
                categories_response = requests.get(
                    f"{os.getenv('KNOWLEDGE_SERVICE_URL', 'http://localhost:5008')}/api/knowledge/categories",
                    timeout=5
                )
                categories = categories_response.json().get('categories', []) if categories_response.ok else []
            except:
                categories = []
            
            # Get user types for access control
            user_types = UserType.query.order_by(UserType.name).all()
            
            return render_template('admin/knowledge/articles/edit.html', article=article, categories=categories, user_types=user_types)
        else:
            flash('مقاله یافت نشد', 'error')
            return redirect(url_for('admin.knowledge_articles_list'))
    except Exception as e:
        logger.error(f"Error editing article: {e}", exc_info=True)
        flash(f'خطا در ویرایش مقاله: {str(e)}', 'error')
        return redirect(url_for('admin.knowledge_articles_list'))


@admin_bp.route('/knowledge/articles/<int:article_id>/attachments', methods=['POST'])
@login_required
@admin_required
def knowledge_article_upload_attachment(article_id):
    """Upload attachment for article"""
    try:
        if 'file' not in request.files:
            return jsonify({"error": "No file provided", "message": "فایلی ارسال نشده است"}), 400
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({"error": "Empty filename", "message": "نام فایل خالی است"}), 400
        
        api_url = f"{os.getenv('KNOWLEDGE_SERVICE_URL', 'http://localhost:5008')}/api/knowledge/articles/{article_id}/attachments"
        token = get_access_token_from_session()
        headers = {'X-Admin-Request': 'true'}
        if token:
            headers['Authorization'] = f'Bearer {token}'
            headers['X-Auth-Token'] = token
        
        # Read file content and prepare for upload
        file.seek(0)  # Reset file pointer
        file_content = file.read()
        file.seek(0)  # Reset again for potential retry
        
        # Prepare files dict for requests
        files = {
            'file': (file.filename, file_content, file.content_type or 'application/octet-stream')
        }
        
        response = requests.post(api_url, files=files, headers=headers, timeout=60)
        
        if response.ok:
            return jsonify(response.json()), 201
        else:
            error_data = {}
            try:
                if response.content:
                    error_data = response.json()
            except:
                error_data = {'message': response.text or 'خطای نامشخص'}
            logger.error(f"Error from knowledge service: {response.status_code} - {error_data}")
            return jsonify({"error": error_data.get("error", "خطای نامشخص"), "message": error_data.get("message", "خطا در آپلود فایل")}), response.status_code
    except Exception as e:
        logger.error(f"Error uploading attachment: {e}", exc_info=True)
        return jsonify({"error": str(e), "message": "خطا در آپلود فایل"}), 500


@admin_bp.route('/knowledge/articles/<int:article_id>/attachments/<int:attachment_id>', methods=['DELETE'])
@login_required
@admin_required
def knowledge_article_delete_attachment(article_id, attachment_id):
    """Delete attachment"""
    try:
        api_url = f"{os.getenv('KNOWLEDGE_SERVICE_URL', 'http://localhost:5008')}/api/knowledge/articles/{article_id}/attachments/{attachment_id}"
        token = get_access_token_from_session()
        headers = {'X-Admin-Request': 'true'}
        if token:
            headers['Authorization'] = f'Bearer {token}'
            headers['X-Auth-Token'] = token
        
        response = requests.delete(api_url, headers=headers, timeout=10)
        
        if response.ok:
            return jsonify({"message": "فایل با موفقیت حذف شد"}), 200
        else:
            error_data = response.json() if response.content else {}
            return jsonify({"error": error_data.get("error", "خطای نامشخص"), "message": error_data.get("message", "خطا در حذف فایل")}), response.status_code
    except Exception as e:
        logger.error(f"Error deleting attachment: {e}", exc_info=True)
        return jsonify({"error": str(e), "message": "خطا در حذف فایل"}), 500


@admin_bp.route('/knowledge/articles/<int:article_id>/attachments/<int:attachment_id>/download')
@login_required
@admin_required
def knowledge_article_download_attachment(article_id, attachment_id):
    """Download attachment"""
    try:
        # First get attachment info
        api_url = f"{os.getenv('KNOWLEDGE_SERVICE_URL', 'http://localhost:5008')}/api/knowledge/articles/{article_id}"
        token = get_access_token_from_session()
        headers = {'X-Admin-Request': 'true'}
        if token:
            headers['Authorization'] = f'Bearer {token}'
            headers['X-Auth-Token'] = token
        
        response = requests.get(api_url, headers=headers, timeout=10)
        if not response.ok:
            flash('مقاله یافت نشد', 'error')
            return redirect(url_for('admin.knowledge_articles_list'))
        
        article = response.json()
        attachment = next((att for att in article.get('attachments', []) if att['id'] == attachment_id), None)
        
        if not attachment:
            flash('فایل یافت نشد', 'error')
            return redirect(url_for('admin.knowledge_article_detail', article_id=article_id))
        
        # Get file from knowledge service
        download_url = f"{os.getenv('KNOWLEDGE_SERVICE_URL', 'http://localhost:5008')}/api/knowledge/articles/{article_id}/attachments/{attachment_id}/download"
        file_response = requests.get(download_url, headers=headers, stream=True, timeout=30)
        
        if file_response.ok:
            return Response(
                file_response.iter_content(chunk_size=8192),
                mimetype=attachment.get('mime_type', 'application/octet-stream'),
                headers={
                    'Content-Disposition': f'attachment; filename="{attachment["filename"]}"'
                }
            )
        else:
            flash('خطا در دانلود فایل', 'error')
            return redirect(url_for('admin.knowledge_article_detail', article_id=article_id))
    except Exception as e:
        logger.error(f"Error downloading attachment: {e}", exc_info=True)
        flash(f'خطا در دانلود فایل: {str(e)}', 'error')
        return redirect(url_for('admin.knowledge_articles_list'))


@admin_bp.route('/knowledge/articles/<int:article_id>/delete', methods=['POST'])
@login_required
@admin_required
def knowledge_article_delete(article_id):
    """Delete article"""
    try:
        api_url = f"{os.getenv('KNOWLEDGE_SERVICE_URL', 'http://localhost:5008')}/api/knowledge/articles/{article_id}"
        token = get_access_token_from_session()
        headers = {'X-Admin-Request': 'true'}  # Flag for admin requests
        if token:
            headers['Authorization'] = f'Bearer {token}'
            headers['X-Auth-Token'] = token
        
        response = requests.delete(api_url, headers=headers, timeout=10)
        
        if response.ok:
            log_action('delete_knowledge_article', 'article', article_id)
            flash('مقاله با موفقیت حذف شد', 'success')
        else:
            error_data = response.json() if response.content else {}
            flash(f'خطا در حذف مقاله: {error_data.get("message", "خطای نامشخص")}', 'error')
    except Exception as e:
        logger.error(f"Error deleting article: {e}", exc_info=True)
        flash(f'خطا در حذف مقاله: {str(e)}', 'error')
    
    return redirect(url_for('admin.knowledge_articles_list'))


@admin_bp.route('/knowledge/articles/export')
@login_required
@admin_required
def knowledge_articles_export():
    """Export articles to JSON/CSV"""
    log_action('export_knowledge_articles')
    
    format_type = request.args.get('format', 'json')  # json or csv
    search = request.args.get('search', '')
    status = request.args.get('status', '')
    category_id = request.args.get('category_id', type=int)
    date_from = request.args.get('date_from', '')
    date_to = request.args.get('date_to', '')
    author_type = request.args.get('author_type', '')
    
    try:
        # Get all articles matching filters
        api_url = f"{os.getenv('KNOWLEDGE_SERVICE_URL', 'http://localhost:5008')}/api/knowledge/articles"
        params = {
            'page': 1,
            'per_page': 10000,  # Get all
        }
        
        if search:
            params['search'] = search
        if status:
            params['status'] = status
        if category_id:
            params['category_id'] = category_id
        if date_from:
            params['date_from'] = date_from
        if date_to:
            params['date_to'] = date_to
        
        token = get_access_token_from_session()
        headers = {'X-Admin-Request': 'true'}  # Flag for admin requests
        if token:
            headers['Authorization'] = f'Bearer {token}'
            headers['X-Auth-Token'] = token
        
        response = requests.get(api_url, params=params, headers=headers, timeout=30)
        
        if response.ok:
            data = response.json()
            articles = data.get('articles', [])
            
            # Filter by author type if specified
            if author_type == 'knowledge_manager':
                user_types = UserType.query.filter_by(name='مسئول مدیریت دانش').all()
                knowledge_manager_type_id = user_types[0].id if user_types else None
                if knowledge_manager_type_id:
                    knowledge_managers = User.query.join(User.user_types).filter(
                        UserType.id == knowledge_manager_type_id
                    ).all()
                    manager_ids = [u.id for u in knowledge_managers]
                    articles = [a for a in articles if a.get('author_id') in manager_ids]
            
            if format_type == 'json':
                # Export as JSON
                export_data = {
                    'export_date': datetime.utcnow().isoformat(),
                    'total_articles': len(articles),
                    'filters': {
                        'search': search,
                        'status': status,
                        'category_id': category_id,
                        'date_from': date_from,
                        'date_to': date_to,
                        'author_type': author_type
                    },
                    'articles': articles
                }
                
                response_obj = Response(
                    json.dumps(export_data, ensure_ascii=False, indent=2),
                    mimetype='application/json',
                    headers={
                        'Content-Disposition': f'attachment; filename=knowledge_articles_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json'
                    }
                )
                return response_obj
            else:
                # Export as CSV
                import csv
                import io
                
                output = io.StringIO()
                writer = csv.writer(output)
                
                # Write header
                writer.writerow(['ID', 'عنوان', 'خلاصه', 'نویسنده', 'دسته‌بندی', 'وضعیت', 'بازدید', 'لایک', 'تاریخ ایجاد', 'تاریخ به‌روزرسانی'])
                
                # Write data
                for article in articles:
                    writer.writerow([
                        article.get('id'),
                        article.get('title', ''),
                        article.get('summary', '')[:100],
                        article.get('author_id'),
                        article.get('category_id'),
                        article.get('status', ''),
                        article.get('views_count', 0),
                        article.get('likes_count', 0),
                        article.get('created_at', ''),
                        article.get('updated_at', '')
                    ])
                
                response_obj = Response(
                    output.getvalue(),
                    mimetype='text/csv; charset=utf-8-sig',
                    headers={
                        'Content-Disposition': f'attachment; filename=knowledge_articles_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'
                    }
                )
                return response_obj
        else:
            flash('خطا در دریافت مقالات', 'error')
            return redirect(url_for('admin.knowledge_articles_list'))
    except Exception as e:
        logger.error(f"Error exporting articles: {e}", exc_info=True)
        flash(f'خطا در export مقالات: {str(e)}', 'error')
        return redirect(url_for('admin.knowledge_articles_list'))


@admin_bp.route('/knowledge/tags')
@login_required
def knowledge_tags_list():
    """Get user's tags (proxy to knowledge service)"""
    # login_required already ensures user is authenticated
    # But let's add extra logging for debugging
    try:
        logger.info(f"knowledge_tags_list: current_user authenticated: {current_user.is_authenticated}, user_id: {current_user.id if current_user.is_authenticated else None}")
        logger.info(f"knowledge_tags_list: session keys: {list(session.keys())}")
    except:
        pass
    
    try:
        api_url = f"{os.getenv('KNOWLEDGE_SERVICE_URL', 'http://localhost:5008')}/api/knowledge/tags"
        token = get_access_token_from_session()
        
        if not token:
            logger.warning("knowledge_tags_list: No token found in session")
            # Return empty tags list instead of error to avoid breaking UI
            return jsonify({'tags': []}), 200
        
        headers = {'X-Admin-Request': 'true'}
        headers['Authorization'] = f'Bearer {token}'
        headers['X-Auth-Token'] = token
        
        logger.info(f"knowledge_tags_list: Fetching tags from {api_url} with token length: {len(token)}")
        response = requests.get(api_url, headers=headers, timeout=10)
        
        if response.ok:
            return response.json(), 200
        else:
            error_data = {}
            try:
                if response.content:
                    error_data = response.json()
            except:
                error_data = {'message': response.text or 'خطای نامشخص'}
            
            logger.error(f"knowledge_tags_list: Error from knowledge service - {response.status_code}: {error_data}")
            # Return empty tags list instead of error to avoid breaking UI
            return jsonify({'tags': []}), 200
    except Exception as e:
        logger.error(f"Error fetching tags: {e}", exc_info=True)
        # Return empty tags list instead of error to avoid breaking UI
        return jsonify({'tags': []}), 200


@admin_bp.route('/knowledge/articles/import', methods=['GET', 'POST'])
@login_required
@admin_required
def knowledge_articles_import():
    """Import articles from backup file"""
    if request.method == 'POST':
        if 'file' not in request.files:
            flash('لطفاً فایل را انتخاب کنید', 'error')
            return redirect(url_for('admin.knowledge_articles_import'))
        
        file = request.files['file']
        if file.filename == '':
            flash('لطفاً فایل را انتخاب کنید', 'error')
            return redirect(url_for('admin.knowledge_articles_import'))
        
        try:
            if file.filename.endswith('.json'):
                # Import from JSON
                data = json.load(file)
                articles = data.get('articles', [])
                
                api_url = f"{os.getenv('KNOWLEDGE_SERVICE_URL', 'http://localhost:5008')}/api/knowledge/articles"
                token = get_access_token_from_session()
                headers = {'Content-Type': 'application/json', 'X-Admin-Request': 'true'}  # Flag for admin requests
                if token:
                    headers['Authorization'] = f'Bearer {token}'
                    headers['X-Auth-Token'] = token
                
                imported_count = 0
                errors = []
                
                for article in articles:
                    try:
                        # Remove id and dates from import
                        article_data = {
                            'title': article.get('title'),
                            'content': article.get('content'),
                            'summary': article.get('summary'),
                            'category_id': article.get('category_id'),
                            'status': article.get('status', 'draft'),
                            'tags': [tag.get('name') for tag in article.get('tags', [])],
                            'author_id': current_user.id if current_user.is_authenticated else article.get('author_id')
                        }
                        
                        response = requests.post(api_url, json=article_data, headers=headers, timeout=10)
                        if response.ok:
                            imported_count += 1
                        else:
                            errors.append(f"مقاله '{article.get('title', 'بدون عنوان')}': {response.json().get('message', 'خطای نامشخص')}")
                    except Exception as e:
                        errors.append(f"مقاله '{article.get('title', 'بدون عنوان')}': {str(e)}")
                
                if imported_count > 0:
                    log_action('import_knowledge_articles', details={'count': imported_count})
                    flash(f'{imported_count} مقاله با موفقیت import شد', 'success')
                if errors:
                    flash(f'{len(errors)} خطا در import: ' + '; '.join(errors[:5]), 'warning')
                
                return redirect(url_for('admin.knowledge_articles_list'))
            else:
                flash('فقط فایل‌های JSON پشتیبانی می‌شوند', 'error')
                return redirect(url_for('admin.knowledge_articles_import'))
        except Exception as e:
            logger.error(f"Error importing articles: {e}", exc_info=True)
            flash(f'خطا در import مقالات: {str(e)}', 'error')
            return redirect(url_for('admin.knowledge_articles_import'))
    
    return render_template('admin/knowledge/articles/import.html')


# ==================== Dashboard Access Management ====================

@admin_bp.route('/dashboard-access')
@login_required
@admin_required
def dashboard_access_list():
    """List dashboard accesses"""
    log_action('view_dashboard_access_list')
    
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    
    # Get filter parameters
    dashboard_id_filter = request.args.get('dashboard_id', '')
    user_id_filter = request.args.get('user_id', '')
    
    # Build query with filters
    query = DashboardAccess.query
    
    if dashboard_id_filter:
        query = query.filter(DashboardAccess.dashboard_id == dashboard_id_filter)
    
    if user_id_filter:
        try:
            user_id = int(user_id_filter)
            query = query.filter(DashboardAccess.user_id == user_id)
        except ValueError:
            pass
    
    # Get all accesses with pagination
    accesses = query.order_by(DashboardAccess.created_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )
    
    # Get all dashboards for filter dropdown
    dashboard_configs = {cfg.dashboard_id: cfg for cfg in DashboardConfig.query.all()}
    
    # Get all users for filter dropdown
    users = User.query.order_by(User.name).all()
    
    # Get unique dashboard IDs from accesses for filter dropdown
    unique_dashboard_ids = db.session.query(DashboardAccess.dashboard_id).distinct().all()
    unique_dashboard_ids = [d[0] for d in unique_dashboard_ids]
    
    return render_template('admin/dashboard_access/list.html', 
                         accesses=accesses,
                         dashboard_configs=dashboard_configs,
                         users=users,
                         unique_dashboard_ids=unique_dashboard_ids,
                         current_dashboard_filter=dashboard_id_filter,
                         current_user_filter=user_id_filter)


@admin_bp.route('/dashboard-access/new', methods=['GET', 'POST'])
@login_required
@admin_required
def dashboard_access_create():
    """Create dashboard access"""
    if request.method == 'POST':
        # Build filter restrictions from individual fields
        filter_restrictions = {}
        
        # Get province codes
        province_codes = request.form.getlist('province_codes')
        if province_codes:
            try:
                filter_restrictions['province_codes'] = [int(code) for code in province_codes if code]
            except (ValueError, TypeError):
                pass
        
        # Get university codes
        university_codes = request.form.getlist('university_codes')
        if university_codes:
            try:
                filter_restrictions['university_codes'] = [int(code) for code in university_codes if code]
            except (ValueError, TypeError):
                pass
        
        # Get faculty codes
        faculty_codes = request.form.getlist('faculty_codes')
        if faculty_codes:
            try:
                filter_restrictions['faculty_codes'] = [int(code) for code in faculty_codes if code]
            except (ValueError, TypeError):
                pass
        
        # If JSON is provided directly (for backward compatibility), use it
        filter_restrictions_json = request.form.get('filter_restrictions')
        if filter_restrictions_json:
            try:
                import json
                json_restrictions = json.loads(filter_restrictions_json)
                if json_restrictions:
                    filter_restrictions = json_restrictions
            except (json.JSONDecodeError, TypeError):
                pass
        
        access = DashboardAccess(
            user_id=request.form.get('user_id', type=int),
            dashboard_id=request.form.get('dashboard_id'),
            can_access=request.form.get('can_access') == 'on',
            filter_restrictions=filter_restrictions if filter_restrictions else {},
            created_by=current_user.id
        )
        
        # Parse Persian calendar date restrictions
        if request.form.get('date_from'):
            date_from_str = request.form.get('date_from').strip()
            if date_from_str:
                try:
                    # Parse Persian calendar date (format: YYYY/MM/DD)
                    date_parts = list(map(int, date_from_str.split('/')))
                    if len(date_parts) == 3:
                        jd = jdatetime.datetime(date_parts[0], date_parts[1], date_parts[2])
                        access.date_from = jd.togregorian()
                except (ValueError, IndexError, AttributeError) as e:
                    logger.error(f"Error parsing date_from: {e}")
        
        if request.form.get('date_to'):
            date_to_str = request.form.get('date_to').strip()
            if date_to_str:
                try:
                    # Parse Persian calendar date (format: YYYY/MM/DD)
                    date_parts = list(map(int, date_to_str.split('/')))
                    if len(date_parts) == 3:
                        jd = jdatetime.datetime(date_parts[0], date_parts[1], date_parts[2], 23, 59, 59)
                        access.date_to = jd.togregorian()
                except (ValueError, IndexError, AttributeError) as e:
                    logger.error(f"Error parsing date_to: {e}")
        
        db.session.add(access)
        db.session.commit()
        log_action('create_dashboard_access', 'dashboard_access', access.id)
        flash('دسترسی با موفقیت ایجاد شد', 'success')
        return redirect(url_for('admin.dashboard_access_list'))
    
    # Get available dashboards
    dashboards = DashboardRegistry.list_all()
    users = User.query.all()
    
    return render_template('admin/dashboard_access/create.html', 
                         dashboards=dashboards, 
                         users=users)


@admin_bp.route('/dashboard-access/<int:access_id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def dashboard_access_edit(access_id):
    """Edit dashboard access"""
    access = DashboardAccess.query.get_or_404(access_id)
    
    if request.method == 'POST':
        access.can_access = request.form.get('can_access') == 'on'
        
        # Build filter restrictions from individual fields
        filter_restrictions = {}
        
        # Get province codes
        province_codes = request.form.getlist('province_codes')
        if province_codes:
            try:
                filter_restrictions['province_codes'] = [int(code) for code in province_codes if code]
            except (ValueError, TypeError):
                pass
        
        # Get university codes
        university_codes = request.form.getlist('university_codes')
        if university_codes:
            try:
                filter_restrictions['university_codes'] = [int(code) for code in university_codes if code]
            except (ValueError, TypeError):
                pass
        
        # Get faculty codes
        faculty_codes = request.form.getlist('faculty_codes')
        if faculty_codes:
            try:
                filter_restrictions['faculty_codes'] = [int(code) for code in faculty_codes if code]
            except (ValueError, TypeError):
                pass
        
        # If JSON is provided directly (for backward compatibility), use it
        filter_restrictions_json = request.form.get('filter_restrictions')
        if filter_restrictions_json:
            try:
                import json
                json_restrictions = json.loads(filter_restrictions_json)
                if json_restrictions:
                    filter_restrictions = json_restrictions
            except (json.JSONDecodeError, TypeError):
                pass
        
        access.filter_restrictions = filter_restrictions if filter_restrictions else {}
        
        # Parse Persian calendar date restrictions
        if request.form.get('date_from'):
            date_from_str = request.form.get('date_from').strip()
            if date_from_str:
                try:
                    # Parse Persian calendar date (format: YYYY/MM/DD)
                    date_parts = list(map(int, date_from_str.split('/')))
                    if len(date_parts) == 3:
                        jd = jdatetime.datetime(date_parts[0], date_parts[1], date_parts[2])
                        access.date_from = jd.togregorian()
                    else:
                        access.date_from = None
                except (ValueError, IndexError, AttributeError) as e:
                    logger.error(f"Error parsing date_from: {e}")
                    access.date_from = None
            else:
                access.date_from = None
        else:
            access.date_from = None
        
        if request.form.get('date_to'):
            date_to_str = request.form.get('date_to').strip()
            if date_to_str:
                try:
                    # Parse Persian calendar date (format: YYYY/MM/DD)
                    date_parts = list(map(int, date_to_str.split('/')))
                    if len(date_parts) == 3:
                        jd = jdatetime.datetime(date_parts[0], date_parts[1], date_parts[2], 23, 59, 59)
                        access.date_to = jd.togregorian()
                    else:
                        access.date_to = None
                except (ValueError, IndexError, AttributeError) as e:
                    logger.error(f"Error parsing date_to: {e}")
                    access.date_to = None
            else:
                access.date_to = None
        else:
            access.date_to = None
        
        db.session.commit()
        log_action('modify_dashboard_access', 'dashboard_access', access_id)
        flash('دسترسی با موفقیت به‌روزرسانی شد', 'success')
        return redirect(url_for('admin.dashboard_access_list'))
    
    dashboards = DashboardRegistry.list_all()
    users = User.query.all()
    
    # Convert dates to Persian calendar for display
    date_from_jalali = None
    date_to_jalali = None
    if access.date_from:
        try:
            date_from_jalali = jdatetime.datetime.fromgregorian(datetime=access.date_from).strftime('%Y/%m/%d')
        except:
            pass
    if access.date_to:
        try:
            date_to_jalali = jdatetime.datetime.fromgregorian(datetime=access.date_to).strftime('%Y/%m/%d')
        except:
            pass
    
    return render_template('admin/dashboard_access/edit.html', 
                         access=access, 
                         dashboards=dashboards, 
                         users=users,
                         date_from_jalali=date_from_jalali,
                         date_to_jalali=date_to_jalali)


# ==================== Access Logs ====================

@admin_bp.route('/logs')
@login_required
@admin_required
def logs_list():
    """List access logs"""
    log_action('view_access_logs')
    
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 50, type=int)
    user_id = request.args.get('user_id', type=int)
    action = request.args.get('action', '')
    
    query = AccessLog.query
    
    if user_id:
        query = query.filter_by(user_id=user_id)
    if action:
        query = query.filter_by(action=action)
    
    logs = query.order_by(AccessLog.created_at.desc())\
        .paginate(page=page, per_page=per_page, error_out=False)
    
    return render_template('admin/logs/list.html', logs=logs, user_id=user_id, action=action)


# ==================== Data Sync Management ====================

@admin_bp.route('/data-sync/test')
@login_required
@admin_required
def data_sync_test():
    """Test endpoint to debug data sync issues"""
    import traceback
    try:
        from flask import jsonify
        result = {
            'status': 'ok',
            'data_sync_count': 0,
            'errors': [],
            'traceback': None
        }
        
        try:
            logger.info("Test endpoint: Querying DataSync...")
            syncs = DataSync.query.all()
            result['data_sync_count'] = len(syncs)
            result['syncs'] = []
            for sync in syncs:
                try:
                    sync_data = {
                        'id': sync.id,
                        'data_source': sync.data_source,
                        'status': sync.status,
                        'has_interval_value': hasattr(sync, 'sync_interval_value'),
                        'has_interval_unit': hasattr(sync, 'sync_interval_unit'),
                    }
                    try:
                        sync_data['interval_display'] = sync.get_interval_display()
                    except Exception as e:
                        sync_data['interval_display_error'] = str(e)
                        sync_data['interval_display_traceback'] = traceback.format_exc()
                    result['syncs'].append(sync_data)
                except Exception as e:
                    error_msg = f"Error processing sync {getattr(sync, 'id', 'unknown')}: {str(e)}"
                    result['errors'].append(error_msg)
                    logger.error(error_msg, exc_info=True)
        except Exception as e:
            error_msg = f"Error querying DataSync: {str(e)}"
            result['errors'].append(error_msg)
            result['traceback'] = traceback.format_exc()
            result['status'] = 'error'
            logger.error(error_msg, exc_info=True)
        
        return jsonify(result)
    except Exception as e:
        logger.error(f"Fatal error in test endpoint: {e}", exc_info=True)
        return jsonify({
            'status': 'error', 
            'message': str(e),
            'traceback': traceback.format_exc()
        }), 500


@admin_bp.route('/data-sync')
@login_required
@admin_required
def data_sync_list():
    """List data syncs"""
    import traceback
    from flask import Response
    
    try:
        logger.info("=" * 50)
        logger.info("Starting data_sync_list route")
        logger.info("=" * 50)
        
        # Try to log action (non-critical)
        try:
            log_action('view_data_syncs')
        except Exception as log_err:
            logger.warning(f"Error logging action: {log_err}")
        
        # Query syncs with error handling
        syncs = []
        try:
            logger.info("Querying DataSync table...")
            all_syncs = DataSync.query.order_by(DataSync.data_source).all()
            logger.info(f"Found {len(all_syncs)} syncs in database")
            
            # Validate each sync object
            validated_syncs = []
            for sync in all_syncs:
                try:
                    # Test if we can access key attributes
                    data_source = sync.data_source
                    status = sync.status
                    interval_value = getattr(sync, 'sync_interval_value', 60)
                    interval_unit = getattr(sync, 'sync_interval_unit', 'minutes')
                    
                    # Test methods
                    try:
                        interval_display = sync.get_interval_display()
                        logger.debug(f"Sync {sync.id}: interval_display = {interval_display}")
                    except Exception as method_err:
                        logger.warning(f"Error calling get_interval_display on sync {sync.id}: {method_err}")
                    
                    validated_syncs.append(sync)
                except Exception as sync_err:
                    logger.error(f"Error validating sync {getattr(sync, 'id', 'unknown')}: {sync_err}", exc_info=True)
                    continue
            syncs = validated_syncs
            logger.info(f"Validated {len(syncs)} syncs")
        except Exception as query_err:
            logger.error(f"Error querying DataSync: {query_err}", exc_info=True)
            logger.error(f"Query error traceback: {traceback.format_exc()}")
            syncs = []
        
        # Check scheduler status
        scheduler_running = False
        try:
            from .scheduler import is_scheduler_running
            scheduler_running = is_scheduler_running()
            logger.info(f"Scheduler running: {scheduler_running}")
        except Exception as e:
            logger.error(f"Error checking scheduler status: {e}", exc_info=True)
            scheduler_running = False
        
        # Render template
        logger.info(f"Rendering template with {len(syncs)} syncs")
        try:
            # Ensure all sync objects are properly initialized
            for sync in syncs:
                # Pre-call methods to catch any errors before template rendering
                try:
                    _ = sync.get_interval_display()
                except Exception as pre_err:
                    logger.warning(f"Pre-check failed for sync {sync.id}: {pre_err}")
            
            result = render_template('admin/data_sync/list.html', syncs=syncs, scheduler_running=scheduler_running)
            logger.info("Template rendered successfully")
            return result
        except Exception as template_err:
            logger.error(f"Error rendering template: {template_err}", exc_info=True)
            logger.error(f"Template error traceback: {traceback.format_exc()}")
            # Try to render a simple error page
            try:
                flash(f'خطا در نمایش لیست همگام‌سازی‌ها: {str(template_err)}', 'error')
                return render_template('admin/data_sync/list.html', syncs=[], scheduler_running=False)
            except Exception as render_err2:
                logger.error(f"Error rendering error page: {render_err2}", exc_info=True)
                from flask import Response
                error_html = f"""
                <html>
                <head><meta charset="utf-8"><title>خطا</title></head>
                <body dir="rtl">
                    <h1>خطای داخلی سرور</h1>
                    <h2>خطا در رندر کردن template:</h2>
                    <pre>{str(template_err)}</pre>
                    <h2>Traceback:</h2>
                    <pre>{traceback.format_exc()}</pre>
                </body>
                </html>
                """
                return Response(error_html, status=500, mimetype='text/html; charset=utf-8')
        
    except Exception as e:
        error_traceback = traceback.format_exc()
        logger.error("=" * 50)
        logger.error(f"FATAL ERROR in data_sync_list: {e}")
        logger.error("=" * 50)
        logger.error(f"Full traceback:\n{error_traceback}")
        logger.error("=" * 50)
        
        try:
            flash(f'خطا در نمایش لیست همگام‌سازی‌ها: {str(e)}', 'error')
            return render_template('admin/data_sync/list.html', syncs=[], scheduler_running=False)
        except Exception as render_err:
            logger.error(f"Error rendering error page: {render_err}", exc_info=True)
            error_html = f"""<!DOCTYPE html>
<html dir="rtl" lang="fa">
<head>
    <meta charset="utf-8">
    <title>خطای سرور</title>
    <style>
        body {{ font-family: Tahoma, Arial; padding: 20px; background: #f5f5f5; }}
        .error-box {{ background: white; padding: 20px; border-radius: 5px; box-shadow: 0 2px 5px rgba(0,0,0,0.1); }}
        h1 {{ color: #d32f2f; }}
        pre {{ background: #f5f5f5; padding: 10px; border-radius: 3px; overflow-x: auto; }}
    </style>
</head>
<body>
    <div class="error-box">
        <h1>خطای داخلی سرور</h1>
        <h2>خطا:</h2>
        <pre>{str(e)}</pre>
        <h2>Traceback:</h2>
        <pre>{error_traceback}</pre>
    </div>
</body>
</html>"""
            return Response(error_html, status=500, mimetype='text/html; charset=utf-8')


@admin_bp.route('/data-sync/<int:sync_id>/sync', methods=['POST'])
@login_required
@admin_required
def data_sync_trigger(sync_id):
    """Trigger manual data sync in background"""
    sync = DataSync.query.get_or_404(sync_id)
    
    # For LMS sync, always perform manual sync (stops continuous sync first)
    if sync.data_source == 'lms':
        log_action('trigger_data_sync', 'data_sync', sync_id, {'data_source': sync.data_source, 'manual': True})
        
        # Import sync handler
        from .sync_handlers import run_lms_sync
        import threading
        from flask import current_app
        
        def run_manual_sync_background():
            """Run manual LMS sync in background thread (will stop continuous sync first)"""
            try:
                with current_app.app_context():
                    run_lms_sync(user_id=current_user.id, sync_id=sync_id, manual_sync=True)
            except Exception as e:
                logger.error(f"Error in background manual sync: {e}", exc_info=True)
        
        # Start manual sync in background thread
        thread = threading.Thread(target=run_manual_sync_background, daemon=True)
        thread.start()
        
        flash('همگام‌سازی دستی LMS شروع شد. در صورت فعال بودن، همگام‌سازی مداوم متوقف و پس از اتمام، دوباره شروع می‌شود.', 'info')
        return redirect(url_for('admin.data_sync_list'))
    
    # Check if sync is already running (for non-LMS syncs)
    if sync.status == 'running':
        flash('همگام‌سازی در حال اجرا است. لطفاً منتظر بمانید.', 'warning')
        return redirect(url_for('admin.data_sync_list'))
    
    log_action('trigger_data_sync', 'data_sync', sync_id, {'data_source': sync.data_source})
    
    # Import sync handler
    from .sync_handlers import run_sync_by_source
    import threading
    from flask import current_app
    
    def run_sync_background():
        """Run sync in background thread"""
        try:
            with current_app.app_context():
                run_sync_by_source(sync.data_source, current_user.id, sync_id=sync_id)
        except Exception as e:
            logger.error(f"Error in background sync: {e}", exc_info=True)
    
    # Start sync in background thread
    thread = threading.Thread(target=run_sync_background, daemon=True)
    thread.start()
    
    flash('همگام‌سازی شروع شد. وضعیت را در جدول زیر مشاهده کنید.', 'info')
    return redirect(url_for('admin.data_sync_list'))


@admin_bp.route('/data-sync/<int:sync_id>/stop', methods=['POST'])
@login_required
@admin_required
def data_sync_stop(sync_id):
    """Stop a running sync"""
    sync = DataSync.query.get_or_404(sync_id)
    
    # For LMS continuous sync, check both status and thread status
    # Allow stopping if either status is 'running' or thread is actually running
    can_stop = False
    if sync.data_source == 'lms':
        from .sync_handlers import _lms_continuous_thread, _lms_continuous_running
        thread_is_alive = _lms_continuous_thread and _lms_continuous_thread.is_alive()
        can_stop = sync.status == 'running' or _lms_continuous_running or thread_is_alive
    else:
        can_stop = sync.status == 'running'
    
    if not can_stop:
        flash('همگام‌سازی در حال اجرا نیست.', 'warning')
        return redirect(url_for('admin.data_sync_list'))
    
    log_action('stop_data_sync', 'data_sync', sync_id, {'data_source': sync.data_source})
    
    # Import sync handler
    from .sync_handlers import stop_sync_by_source
    
    success, message = stop_sync_by_source(sync.data_source, sync_id=sync_id)
    
    if success:
        flash(message, 'success')
    else:
        flash(message, 'error')
    
    return redirect(url_for('admin.data_sync_list'))


@admin_bp.route('/data-sync/<int:sync_id>/restart', methods=['POST'])
@login_required
@admin_required
def data_sync_restart(sync_id):
    """Restart a sync (stop if running, then start)"""
    sync = DataSync.query.get_or_404(sync_id)
    
    log_action('restart_data_sync', 'data_sync', sync_id, {'data_source': sync.data_source})
    
    # Import sync handlers
    from .sync_handlers import stop_sync_by_source, run_sync_by_source
    import threading
    from flask import current_app
    
    # Stop if running
    if sync.status == 'running':
        stop_sync_by_source(sync.data_source, sync_id=sync_id)
        import time
        time.sleep(1)  # Wait a bit for stop to complete
    
    # Start sync in background thread
    def run_sync_background():
        """Run sync in background thread"""
        try:
            with current_app.app_context():
                run_sync_by_source(sync.data_source, current_user.id, sync_id=sync_id)
        except Exception as e:
            logger.error(f"Error in background sync: {e}", exc_info=True)
    
    thread = threading.Thread(target=run_sync_background, daemon=True)
    thread.start()
    
    flash('همگام‌سازی دوباره راه‌اندازی شد.', 'success')
    return redirect(url_for('admin.data_sync_list'))


@admin_bp.route('/scheduler/start', methods=['POST'])
@login_required
@admin_required
def scheduler_start():
    """Start the auto-sync scheduler"""
    try:
        from .scheduler import start_scheduler, is_scheduler_running
        
        if is_scheduler_running():
            flash('Scheduler در حال اجرا است.', 'info')
        else:
            start_scheduler()
            log_action('start_scheduler', 'system', None, {})
            flash('Scheduler با موفقیت شروع شد.', 'success')
    except Exception as e:
        logger.error(f"Error starting scheduler: {e}", exc_info=True)
        flash(f'خطا در شروع Scheduler: {str(e)}', 'error')
    
    return redirect(url_for('admin.data_sync_list'))


@admin_bp.route('/scheduler/stop', methods=['POST'])
@login_required
@admin_required
def scheduler_stop():
    """Stop the auto-sync scheduler"""
    try:
        from .scheduler import stop_scheduler, is_scheduler_running
        
        if not is_scheduler_running():
            flash('Scheduler در حال اجرا نیست.', 'info')
        else:
            stop_scheduler()
            log_action('stop_scheduler', 'system', None, {})
            flash('Scheduler با موفقیت متوقف شد.', 'success')
    except Exception as e:
        logger.error(f"Error stopping scheduler: {e}", exc_info=True)
        flash(f'خطا در توقف Scheduler: {str(e)}', 'error')
    
    return redirect(url_for('admin.data_sync_list'))


@admin_bp.route('/data-sync/<int:sync_id>/progress')
@login_required
@admin_required
def data_sync_progress(sync_id):
    """Get real-time progress of sync operation"""
    from .sync_progress import get_sync_progress
    
    progress = get_sync_progress(sync_id)
    
    if not progress:
        # Check database status
        sync = DataSync.query.get_or_404(sync_id)
        return jsonify({
            'status': sync.status,
            'progress': 100 if sync.status in ['success', 'failed'] else 0,
            'current_step': sync.status,
            'records_processed': sync.records_synced,
            'error_message': sync.error_message,
            'logs': []
        })
    
    return jsonify(progress)


@admin_bp.route('/data-sync/logs')
@login_required
@admin_required
def sync_logs():
    """View auto-sync logs"""
    log_action('view_sync_logs')
    
    # Get logs related to auto-sync
    logs = AccessLog.query.filter(
        AccessLog.action.in_(['auto_sync_started', 'auto_sync_completed', 'auto_sync_failed', 'auto_sync_error'])
    ).order_by(AccessLog.created_at.desc()).limit(100).all()
    
    return render_template('admin/data_sync/logs.html', logs=logs)


@admin_bp.route('/data-sync/<int:sync_id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def data_sync_edit(sync_id):
    """Edit data sync configuration"""
    sync = DataSync.query.get_or_404(sync_id)
    
    if request.method == 'POST':
        # Validate required fields
        api_endpoint = request.form.get('api_endpoint', '').strip()
        if not api_endpoint:
            flash('لطفاً API Endpoint را وارد کنید', 'error')
            return render_template('admin/data_sync/edit.html', sync=sync)
        
        sync.auto_sync_enabled = request.form.get('auto_sync_enabled') == 'on'
        sync.sync_interval_value = request.form.get('sync_interval_value', type=int) or 60
        sync.sync_interval_unit = request.form.get('sync_interval_unit', 'minutes')
        sync.api_base_url = request.form.get('api_base_url', '').strip() or None
        sync.api_endpoint = api_endpoint
        sync.api_method = request.form.get('api_method', 'GET')
        sync.api_username = request.form.get('api_username', '').strip() or None
        # Only update password if provided (to allow keeping existing password)
        api_password = request.form.get('api_password', '').strip()
        if api_password:
            sync.api_password = api_password
        
        # Calculate next sync time
        if sync.auto_sync_enabled and sync.last_sync_at:
            interval_minutes = sync.get_interval_minutes()
            sync.next_sync_at = sync.last_sync_at + timedelta(minutes=interval_minutes)
        elif not sync.auto_sync_enabled:
            sync.next_sync_at = None
        
        db.session.commit()
        log_action('modify_data_sync', 'data_sync', sync_id, {
            'auto_sync_enabled': sync.auto_sync_enabled,
            'sync_interval_value': sync.sync_interval_value,
            'sync_interval_unit': sync.sync_interval_unit,
            'api_endpoint': sync.api_endpoint,
            'api_method': sync.api_method
        })
        flash('تنظیمات همگام‌سازی با موفقیت به‌روزرسانی شد', 'success')
        return redirect(url_for('admin.data_sync_list'))
    
    return render_template('admin/data_sync/edit.html', sync=sync)


@admin_bp.route('/data-sync/<int:sync_id>/test-connection', methods=['POST'])
@login_required
@admin_required
def test_api_connection(sync_id):
    """Test API connection for a sync configuration"""
    sync = DataSync.query.get_or_404(sync_id)
    
    try:
        import requests
        
        # Get values from form data (if provided) or use sync object values
        api_base_url = request.form.get('api_base_url', '').strip() or sync.api_base_url
        api_endpoint = request.form.get('api_endpoint', '').strip() or sync.api_endpoint
        api_username = request.form.get('api_username', '').strip() or sync.api_username
        
        # Handle password: if form password is empty, use sync password
        form_password = request.form.get('api_password', '').strip()
        api_password = form_password if form_password else (sync.api_password or '')
        
        # Log for debugging
        logger.info(f"Test connection - Base URL: {api_base_url}, Endpoint: {api_endpoint}, Username: {api_username}, Password provided: {bool(api_password)}")
        
        # For faculty and students, test login first
        if sync.data_source in ['faculty', 'students']:
            if not api_base_url or not api_username or not api_password:
                missing_fields = []
                if not api_base_url:
                    missing_fields.append('Base URL')
                if not api_username:
                    missing_fields.append('Username')
                if not api_password:
                    missing_fields.append('Password')
                return jsonify({
                    'success': False,
                    'message': f'اطلاعات احراز هویت کامل نیست. فیلدهای خالی: {", ".join(missing_fields)}'
                }), 400
            
            # Test login
            login_url = f"{api_base_url}/Login"
            login_payload = {
                "userName": api_username,
                "password": api_password
            }
            
            try:
                response = requests.post(login_url, json=login_payload, timeout=10)
                response.raise_for_status()
                data = response.json()
                
                if 'data' not in data or 'token' not in data['data']:
                    return jsonify({
                        'success': False,
                        'message': 'خطا در دریافت Token: پاسخ API نامعتبر است'
                    }), 400
                
                token = data['data']['token']
                
                # Test endpoint with token
                headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
                
                # Build proper test payload based on data source
                if sync.data_source == 'students':
                    # Students API requires codePardis, term, paging, and Filter
                    # Try to get a valid pardis_code from database
                    try:
                        import sqlite3
                        import os
                        BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                        db_path = os.path.join(BASE_DIR, 'access_control.db')
                        if os.path.exists(db_path):
                            conn = sqlite3.connect(db_path)
                            cursor = conn.cursor()
                            cursor.execute("SELECT pardis_code FROM pardis LIMIT 1")
                            row = cursor.fetchone()
                            conn.close()
                            test_pardis = str(row[0]) if row else "1110"  # Default to a known valid code
                        else:
                            test_pardis = "1110"  # Default to a known valid code
                    except Exception as db_err:
                        logger.warning(f"Could not read pardis_code from DB: {db_err}")
                        test_pardis = "1110"  # Default to a known valid code
                    
                    # Use a valid term format
                    # Term format: last 3 digits of year + term number
                    # e.g., year 1400 -> 400, term 1 -> 4001
                    # e.g., year 1404 -> 404, term 1 -> 4041
                    # Use a recent term (1404, term 1 = 4041)
                    # Make sure codePardis and term are strings
                    test_payload = {
                        "codePardis": str(test_pardis).strip(),
                        "term": "4041",  # Year 1404, Term 1 (more likely to have data)
                        "paging": {
                            "pageNumber": 1,
                            "pageSize": 1
                        },
                        "Filter": {}
                    }
                    
                    # Validate payload before sending
                    if not test_payload["codePardis"] or not test_payload["term"]:
                        return jsonify({
                            'success': False,
                            'message': f'خطا در ساخت payload: codePardis={test_payload["codePardis"]}, term={test_payload["term"]}'
                        }), 400
                elif sync.data_source == 'faculty':
                    # Faculty API only requires paging
                    test_payload = {
                        "pageNumber": 1,
                        "pageSize": 1
                    }
                else:
                    test_payload = {"pageNumber": 1, "pageSize": 1}
                
                # Log the request for debugging
                logger.info(f"Testing API connection for {sync.data_source}")
                logger.info(f"Endpoint: {api_endpoint}")
                logger.info(f"Payload: {test_payload}")
                logger.info(f"Headers: {headers}")
                
                endpoint_response = requests.post(
                    api_endpoint,
                    json=test_payload,
                    headers=headers,
                    timeout=10
                )
                
                # Log response for debugging
                logger.info(f"Response status: {endpoint_response.status_code}")
                logger.info(f"Response headers: {dict(endpoint_response.headers)}")
                logger.info(f"Response text (first 1000 chars): {endpoint_response.text[:1000]}")
                
                # Check status before raising
                if endpoint_response.status_code != 200:
                    # Try to parse error response
                    try:
                        error_data = endpoint_response.json()
                        logger.error(f"API Error Response: {error_data}")
                    except:
                        logger.error(f"API Error Response (raw): {endpoint_response.text}")
                
                endpoint_response.raise_for_status()
                
                return jsonify({
                    'success': True,
                    'message': f'اتصال موفق! Token دریافت شد و endpoint پاسخ داد. (Status: {endpoint_response.status_code})'
                })
                
            except requests.exceptions.Timeout:
                return jsonify({
                    'success': False,
                    'message': 'Timeout: سرور پاسخ نداد. لطفاً اتصال اینترنت و آدرس API را بررسی کنید.'
                }), 400
            except requests.exceptions.ConnectionError:
                return jsonify({
                    'success': False,
                    'message': 'خطا در اتصال: نمی‌توان به سرور متصل شد. لطفاً آدرس API را بررسی کنید.'
                }), 400
            except requests.exceptions.HTTPError as e:
                if e.response.status_code == 401:
                    return jsonify({
                        'success': False,
                        'message': 'خطا در احراز هویت: Username یا Password اشتباه است.'
                    }), 400
                else:
                    # Try to parse error response for better error message
                    error_msg = f'خطای HTTP {e.response.status_code}'
                    error_details = []
                    
                    try:
                        error_data = e.response.json()
                        error_msg = error_data.get('title', error_msg)
                        
                        # Extract validation errors if available
                        if 'errors' in error_data:
                            errors = error_data['errors']
                            if errors:
                                # errors can be a dict or a string or a list
                                if isinstance(errors, dict):
                                    for field, messages in errors.items():
                                        if isinstance(messages, list):
                                            error_details.append(f"{field}: {', '.join(str(m) for m in messages)}")
                                        else:
                                            error_details.append(f"{field}: {messages}")
                                elif isinstance(errors, str):
                                    error_details.append(f"خطا: {errors}")
                                elif isinstance(errors, list):
                                    error_details.append(f"خطاها: {', '.join(str(e) for e in errors)}")
                                else:
                                    error_details.append(f"خطاهای validation: {str(errors)}")
                            else:
                                # errors field exists but is empty/null
                                error_details.append("خطاهای validation (بدون جزئیات - فیلد errors خالی است)")
                        
                        # Also check for 'message' field
                        if 'message' in error_data and error_data['message']:
                            error_details.append(f"پیام: {error_data['message']}")
                        
                        # Include traceId if available for debugging
                        if 'traceId' in error_data:
                            error_details.append(f"TraceId: {error_data['traceId']}")
                        
                        # Include full error data for debugging
                        logger.error(f"Full error response: {error_data}")
                            
                    except Exception as parse_err:
                        # If JSON parsing fails, use raw text
                        error_text = e.response.text[:1000] if e.response.text else ''
                        error_details.append(f"پاسخ خام: {error_text}")
                        logger.error(f"Error parsing error response: {parse_err}")
                        logger.error(f"Raw response: {e.response.text}")
                    
                    full_message = error_msg
                    if error_details:
                        full_message += f" | جزئیات: {' | '.join(error_details)}"
                    else:
                        # If no details, include the raw response
                        try:
                            raw_error = e.response.json()
                            full_message += f" | پاسخ کامل: {str(raw_error)[:500]}"
                        except:
                            full_message += f" | پاسخ خام: {e.response.text[:500]}"
                    
                    return jsonify({
                        'success': False,
                        'message': full_message
                    }), 400
            except Exception as e:
                return jsonify({
                    'success': False,
                    'message': f'خطا: {str(e)}'
                }), 400
        
        # For LMS, just test endpoint accessibility
        elif sync.data_source == 'lms':
            if not api_endpoint:
                return jsonify({
                    'success': False,
                    'message': 'API Endpoint تعریف نشده است'
                }), 400
            
            try:
                response = requests.get(api_endpoint, timeout=10, verify=False)
                response.raise_for_status()
                return jsonify({
                    'success': True,
                    'message': f'اتصال موفق! Endpoint پاسخ داد. (Status: {response.status_code})'
                })
            except Exception as e:
                return jsonify({
                    'success': False,
                    'message': f'خطا در اتصال: {str(e)}'
                }), 400
        
        else:
            return jsonify({
                'success': False,
                'message': 'نوع منبع داده پشتیبانی نشده برای تست'
            }), 400
            
    except Exception as e:
        logger.error(f"Error testing connection: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'message': f'خطای غیرمنتظره: {str(e)}'
        }), 500


# ==================== Dashboard Configuration ====================

@admin_bp.route('/dashboards')
@login_required
@admin_required
def dashboards_list():
    """List dashboard configurations"""
    log_action('view_dashboard_configs')
    
    # Get dashboards from registry
    registry_dashboards = DashboardRegistry.list_all()
    
    # Get configurations from database
    configs = {cfg.dashboard_id: cfg for cfg in DashboardConfig.query.all()}
    
    # Merge registry dashboards with configs
    dashboards = []
    for dashboard in registry_dashboards:
        config = configs.get(dashboard.dashboard_id)
        dashboards.append({
            'dashboard': dashboard,
            'config': config
        })
    
    return render_template('admin/dashboards/list.html', dashboards=dashboards)


@admin_bp.route('/debug/user-access/<sso_id>')
@login_required
@admin_required
def debug_user_access(sso_id):
    """Debug endpoint to check user dashboard access"""
    user = User.query.filter_by(sso_id=sso_id.lower()).first()
    if not user:
        return jsonify({"error": f"User with SSO ID '{sso_id}' not found"}), 404
    
    # Check admin status
    is_admin = user.is_admin()
    
    # Get dashboard access records
    dashboard_accesses = DashboardAccess.query.filter_by(user_id=user.id).all()
    
    # Get public dashboards
    public_dashboards = DashboardConfig.query.filter_by(is_public=True).all()
    
    # Try to create user context
    try:
        from dashboards.context import UserContext
        user_context = UserContext(user, {})
        access_level = user_context.access_level.value
    except Exception as e:
        access_level = f"Error: {str(e)}"
    
    result = {
        "user": {
            "id": user.id,
            "name": user.name,
            "sso_id": user.sso_id,
            "email": user.email,
            "is_admin": is_admin,
            "access_level": access_level,
            "access_levels": [acc.level for acc in user.access_levels]
        },
        "dashboard_accesses": [
            {
                "dashboard_id": acc.dashboard_id,
                "can_access": acc.can_access,
                "filter_restrictions": acc.filter_restrictions,
                "date_from": acc.date_from.isoformat() if acc.date_from else None,
                "date_to": acc.date_to.isoformat() if acc.date_to else None
            }
            for acc in dashboard_accesses
        ],
        "public_dashboards": [
            {
                "dashboard_id": cfg.dashboard_id,
                "title": cfg.title
            }
            for cfg in public_dashboards
        ],
        "summary": {
            "has_admin_access": is_admin,
            "has_explicit_access": len([a for a in dashboard_accesses if a.can_access]) > 0,
            "has_public_access": len(public_dashboards) > 0,
            "can_access_dashboards": is_admin or len([a for a in dashboard_accesses if a.can_access]) > 0 or len(public_dashboards) > 0
        }
    }
    
    return jsonify(result)


@admin_bp.route('/dashboards/<dashboard_id>/config', methods=['GET', 'POST'])
@login_required
@admin_required
def dashboard_config_edit(dashboard_id):
    """Edit dashboard configuration"""
    dashboard = DashboardRegistry.get(dashboard_id)
    if not dashboard:
        flash('داشبورد یافت نشد', 'error')
        return redirect(url_for('admin.dashboards_list'))
    
    config = DashboardConfig.query.filter_by(dashboard_id=dashboard_id).first()
    
    if request.method == 'POST':
        if not config:
            config = DashboardConfig(
                dashboard_id=dashboard_id,
                created_by=current_user.id
            )
            db.session.add(config)
        
        config.title = request.form.get('title', dashboard.title)
        config.description = request.form.get('description', dashboard.description or '')
        config.icon = request.form.get('icon')
        config.order = request.form.get('order', type=int) or 0
        config.is_active = request.form.get('is_active') == 'on'
        config.is_public = request.form.get('is_public') == 'on'
        config.cache_ttl_seconds = request.form.get('cache_ttl_seconds', type=int) or 300
        config.refresh_interval_seconds = request.form.get('refresh_interval_seconds', type=int) or None
        
        db.session.commit()
        log_action('modify_dashboard_config', 'dashboard', dashboard_id)
        flash('تنظیمات داشبورد با موفقیت به‌روزرسانی شد', 'success')
        return redirect(url_for('admin.dashboards_list'))
    
    return render_template('admin/dashboards/config.html', 
                         dashboard=dashboard, 
                         config=config)


# ==================== Dashboard Template Editing ====================

@admin_bp.route('/dashboards/templates')
@login_required
@admin_required
def dashboard_templates_list():
    """List all dashboard template files"""
    log_action('view_dashboard_templates')
    
    # Get template directory path
    base_dir = Path(__file__).parent.parent
    templates_dir = base_dir / 'templates' / 'dashboards'
    
    # Get all HTML files in dashboards directory
    templates = []
    if templates_dir.exists():
        for file_path in templates_dir.glob('*.html'):
            # Skip files starting with underscore (partial templates)
            if not file_path.name.startswith('_'):
                templates.append({
                    'name': file_path.name,
                    'size': file_path.stat().st_size,
                    'modified': datetime.fromtimestamp(file_path.stat().st_mtime),
                    'dashboard_id': file_path.stem  # filename without extension
                })
    
    # Sort by name
    templates.sort(key=lambda x: x['name'])
    
    # Get dashboards from registry to match with templates
    registry_dashboards = {d.dashboard_id: d for d in DashboardRegistry.list_all()}
    
    # Add dashboard info to templates
    for template in templates:
        dashboard_id = template['dashboard_id']
        template['dashboard'] = registry_dashboards.get(dashboard_id)
    
    return render_template('admin/dashboards/templates_list.html', templates=templates)


@admin_bp.route('/dashboards/templates/<template_name>')
@login_required
@admin_required
def dashboard_template_view(template_name):
    """View a dashboard template file"""
    # Wrap entire function to catch all errors - including decorator errors
    try:
        logger.info(f"dashboard_template_view called for: {template_name}")
        try:
            log_action('view_dashboard_template', 'template', template_name)
        except Exception as e:
            logger.warning(f"Error logging action: {e}")
        
        try:
            # Security: Only allow HTML files
            if not template_name.endswith('.html') or '..' in template_name or '/' in template_name:
                flash('نام فایل نامعتبر است', 'error')
                return redirect(url_for('admin.dashboard_templates_list'))
            
            # Get template directory path
            base_dir = Path(__file__).parent.parent
            template_path = base_dir / 'templates' / 'dashboards' / template_name
            
            if not template_path.exists():
                flash('تمپلیت یافت نشد', 'error')
                return redirect(url_for('admin.dashboard_templates_list'))
            
            # Read template content
            try:
                with open(template_path, 'r', encoding='utf-8') as f:
                    content = f.read()
            except Exception as e:
                logger.error(f"Error reading template {template_name}: {e}", exc_info=True)
                flash(f'خطا در خواندن فایل: {str(e)}', 'error')
                return redirect(url_for('admin.dashboard_templates_list'))
            
            # Get file info
            file_stat = None
            file_size = 0
            try:
                file_stat = template_path.stat()
                file_size = file_stat.st_size if file_stat else 0
            except Exception as e:
                logger.warning(f"Error getting file stats: {e}")
                file_size = 0
            
            dashboard_id = template_path.stem
            dashboard = None
            try:
                dashboard = DashboardRegistry.get(dashboard_id)
            except Exception as e:
                logger.warning(f"Could not get dashboard {dashboard_id} from registry: {e}")
            
            # Get file modification time safely
            modified_time = None
            try:
                if file_stat:
                    modified_time = datetime.fromtimestamp(file_stat.st_mtime)
            except (OSError, ValueError, AttributeError) as e:
                logger.warning(f"Error getting file modification time: {e}")
                modified_time = datetime.now()
            
            # Extract chart information from template content
            charts_list = extract_charts_from_template(content)
            
            # Render template with error handling
            try:
                # Ensure file_size is a number
                if file_size is None:
                    file_size = 0
                file_size = float(file_size) if file_size else 0.0
                
                return render_template('admin/dashboards/template_edit.html',
                                     template_name=template_name,
                                     content=content,
                                     dashboard=dashboard,
                                     file_size=file_size,
                                     modified_time=modified_time,
                                     charts_list=charts_list)
            except Exception as render_err:
                logger.error(f"Error rendering template_edit.html for {template_name}: {render_err}", exc_info=True)
                import traceback
                error_traceback = traceback.format_exc()
                logger.error(f"Template render traceback: {error_traceback}")
                
                # Return error page
                from flask import Response
                error_html = f"""<!DOCTYPE html>
<html dir="rtl" lang="fa">
<head>
    <meta charset="utf-8">
    <title>خطا در ویرایش تمپلیت</title>
    <style>
        body {{ font-family: Tahoma, Arial; padding: 20px; background: #f5f5f5; }}
        .error-box {{ background: white; padding: 20px; border-radius: 5px; box-shadow: 0 2px 5px rgba(0,0,0,0.1); }}
        h1 {{ color: #d32f2f; }}
        pre {{ background: #f5f5f5; padding: 10px; border-radius: 3px; overflow-x: auto; font-size: 12px; }}
    </style>
</head>
<body>
    <div class="error-box">
        <h1>خطا در نمایش صفحه ویرایش</h1>
        <p><strong>تمپلیت:</strong> {template_name}</p>
        <p><strong>خطا:</strong> {str(render_err)}</p>
        <details>
            <summary>جزئیات خطا (برای توسعه‌دهندگان)</summary>
            <pre>{error_traceback}</pre>
        </details>
        <p><a href="/admin/dashboards/templates">بازگشت به لیست تمپلیت‌ها</a></p>
    </div>
</body>
</html>"""
                return Response(error_html, status=500, mimetype='text/html; charset=utf-8')
            
        except Exception as e:
            logger.error(f"Fatal error in dashboard_template_view for {template_name}: {e}", exc_info=True)
            import traceback
            error_traceback = traceback.format_exc()
            logger.error(f"Fatal error traceback: {error_traceback}")
            
            from flask import Response
            error_html = f"""<!DOCTYPE html>
<html dir="rtl" lang="fa">
<head>
    <meta charset="utf-8">
    <title>خطا در ویرایش تمپلیت</title>
    <style>
        body {{ font-family: Tahoma, Arial; padding: 20px; background: #f5f5f5; }}
        .error-box {{ background: white; padding: 20px; border-radius: 5px; box-shadow: 0 2px 5px rgba(0,0,0,0.1); }}
        h1 {{ color: #d32f2f; }}
        pre {{ background: #f5f5f5; padding: 10px; border-radius: 3px; overflow-x: auto; font-size: 12px; }}
    </style>
</head>
<body>
    <div class="error-box">
        <h1>خطای غیرمنتظره</h1>
        <p><strong>تمپلیت:</strong> {template_name}</p>
        <p><strong>خطا:</strong> {str(e)}</p>
        <details>
            <summary>جزئیات خطا (برای توسعه‌دهندگان)</summary>
            <pre>{error_traceback}</pre>
        </details>
        <p><a href="/admin/dashboards/templates">بازگشت به لیست تمپلیت‌ها</a></p>
    </div>
</body>
</html>"""
            return Response(error_html, status=500, mimetype='text/html; charset=utf-8')
    except Exception as e:
        logger.error(f"Fatal error in dashboard_template_view for {template_name}: {e}", exc_info=True)
        import traceback
        error_traceback = traceback.format_exc()
        logger.error(f"Fatal error traceback: {error_traceback}")
        
        from flask import Response
        error_html = f"""<!DOCTYPE html>
<html dir="rtl" lang="fa">
<head>
    <meta charset="utf-8">
    <title>خطا در ویرایش تمپلیت</title>
    <style>
        body {{ font-family: Tahoma, Arial; padding: 20px; background: #f5f5f5; }}
        .error-box {{ background: white; padding: 20px; border-radius: 5px; box-shadow: 0 2px 5px rgba(0,0,0,0.1); }}
        h1 {{ color: #d32f2f; }}
        pre {{ background: #f5f5f5; padding: 10px; border-radius: 3px; overflow-x: auto; font-size: 12px; }}
    </style>
</head>
<body>
    <div class="error-box">
        <h1>خطای غیرمنتظره</h1>
        <p><strong>تمپلیت:</strong> {template_name}</p>
        <p><strong>خطا:</strong> {str(e)}</p>
        <details>
            <summary>جزئیات خطا (برای توسعه‌دهندگان)</summary>
            <pre>{error_traceback}</pre>
        </details>
        <p><a href="/admin/dashboards/templates">بازگشت به لیست تمپلیت‌ها</a></p>
    </div>
</body>
</html>"""
        return Response(error_html, status=500, mimetype='text/html; charset=utf-8')


@admin_bp.route('/dashboards/templates/<template_name>/validate', methods=['POST'])
@login_required
@admin_required
def dashboard_template_validate(template_name):
    """Validate HTML, CSS and JavaScript code in template"""
    try:
        log_action('validate_dashboard_template', 'template', template_name)
        
        # Security: Only allow HTML files
        if not template_name.endswith('.html') or '..' in template_name or '/' in template_name:
            return jsonify({
                'success': False,
                'message': 'نام فایل نامعتبر است'
            }), 400
        
        # Get content from request
        if request.is_json:
            data = request.get_json()
            content = data.get('content', '')
        else:
            content = request.form.get('content', '')
        
        if not content:
            return jsonify({
                'success': False,
                'message': 'محتوای تمپلیت خالی است'
            }), 400
        
        # Validate code
        html_errors = validate_html(content)
        css_errors = validate_css(content)
        js_errors = validate_javascript(content)
        
        return jsonify({
            'success': True,
            'html_errors': html_errors,
            'css_errors': css_errors,
            'js_errors': js_errors
        })
    except Exception as e:
        logger.error(f"Error validating template {template_name}: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'message': f'خطا در بررسی کدها: {str(e)}'
        }), 500


@admin_bp.route('/dashboards/templates/<template_name>/edit', methods=['POST'])
@login_required
@admin_required
def dashboard_template_save(template_name):
    """Save changes to a dashboard template file"""
    log_action('edit_dashboard_template', 'template', template_name)
    
    # Security: Only allow HTML files
    if not template_name.endswith('.html') or '..' in template_name or '/' in template_name:
        return jsonify({
            'success': False,
            'message': 'نام فایل نامعتبر است'
        }), 400
    
    # Get template directory path
    base_dir = Path(__file__).parent.parent
    template_path = base_dir / 'templates' / 'dashboards' / template_name
    
    if not template_path.exists():
        return jsonify({
            'success': False,
            'message': 'تمپلیت یافت نشد'
        }), 404
    
    # Get content from request
    if request.is_json:
        data = request.get_json()
        content = data.get('content', '')
    else:
        content = request.form.get('content', '')
    
    if not content:
        return jsonify({
            'success': False,
            'message': 'محتوای تمپلیت خالی است'
        }), 400
    
    # Create backup before saving
    try:
        backup_path = template_path.with_suffix('.html.backup')
        shutil.copy2(template_path, backup_path)
    except Exception as e:
        logger.warning(f"Could not create backup for {template_name}: {e}")
    
    # Save template
    try:
        with open(template_path, 'w', encoding='utf-8') as f:
            f.write(content)
        
        # Update modification time
        template_path.touch()
        
        logger.info(f"Template {template_name} updated by user {current_user.id}")
        
        return jsonify({
            'success': True,
            'message': 'تمپلیت با موفقیت به‌روزرسانی شد',
            'modified_time': datetime.now().isoformat()
        })
    except Exception as e:
        logger.error(f"Error saving template {template_name}: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'message': f'خطا در ذخیره فایل: {str(e)}'
        }), 500


@admin_bp.route('/dashboards/templates/<template_name>/preview', methods=['GET'])
@login_required
@admin_required
def dashboard_template_preview(template_name):
    """Preview a dashboard template (read-only view)"""
    log_action('preview_dashboard_template', 'template', template_name)
    
    # Security: Only allow HTML files
    if not template_name.endswith('.html') or '..' in template_name or '/' in template_name:
        flash('نام فایل نامعتبر است', 'error')
        return redirect(url_for('admin.dashboard_templates_list'))
    
    # Get template directory path
    base_dir = Path(__file__).parent.parent
    template_path = base_dir / 'templates' / 'dashboards' / template_name
    
    if not template_path.exists():
        flash('تمپلیت یافت نشد', 'error')
        return redirect(url_for('admin.dashboard_templates_list'))
    
    # Read template content
    try:
        with open(template_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception as e:
        logger.error(f"Error reading template {template_name}: {e}", exc_info=True)
        flash(f'خطا در خواندن فایل: {str(e)}', 'error')
        return redirect(url_for('admin.dashboard_templates_list'))
    
    dashboard_id = template_path.stem
    
    return render_template('admin/dashboards/template_preview.html',
                         template_name=template_name,
                         content=content,
                         dashboard_id=dashboard_id)


# ==================== Chart Configuration API ====================

@admin_bp.route('/dashboards/templates/<template_name>/charts', methods=['GET'])
@login_required
@admin_required
def dashboard_template_charts(template_name):
    """Get chart configurations for a template"""
    try:
        log_action('view_chart_configs', 'template', template_name)
    except Exception as e:
        logger.warning(f"Error logging action: {e}")
    
    try:
        # Security check
        if not template_name.endswith('.html') or '..' in template_name or '/' in template_name:
            return jsonify({'success': False, 'message': 'نام فایل نامعتبر است'}), 400
        
        # Get template path
        base_dir = Path(__file__).parent.parent
        template_path = base_dir / 'templates' / 'dashboards' / template_name
        
        if not template_path.exists():
            return jsonify({'success': False, 'message': 'تمپلیت یافت نشد'}), 404
        
        # Read template content
        try:
            with open(template_path, 'r', encoding='utf-8') as f:
                content = f.read()
        except Exception as e:
            logger.error(f"Error reading template {template_name}: {e}", exc_info=True)
            return jsonify({'success': False, 'message': f'خطا در خواندن فایل: {str(e)}'}), 500
        
        # Get dashboard_id from template name (e.g., 'd1.html' -> 'd1')
        dashboard_id = template_path.stem
        
        # Try to get actual data from dashboard
        dashboard_data = {}
        try:
            from dashboards.context import UserContext
            # Create admin context for full access
            admin_context = UserContext(current_user, {})
            admin_context.access_level = admin_context._determine_access_level()
            
            # Get dashboard from registry
            dashboard = DashboardRegistry.get(dashboard_id)
            if dashboard:
                # Get actual data from dashboard
                dashboard_data = dashboard.get_data(admin_context, filters={})
                logger.info(f"Retrieved actual data for dashboard {dashboard_id}")
        except Exception as e:
            logger.warning(f"Could not get actual data for dashboard {dashboard_id}: {e}")
            dashboard_data = {}
        
        # Parse charts from template
        import re
        charts = []
        
        # Find all canvas elements with id (excluding those in HTML comments)
        canvas_pattern = r'<canvas\s+id=["\']([^"\']+)["\']'
        all_canvas_matches = re.findall(canvas_pattern, content, re.IGNORECASE)
        
        # Filter out canvas elements that are inside HTML comments
        canvas_matches = []
        for chart_id in all_canvas_matches:
            # Find the canvas element with this id
            # Use exact match to ensure chart_id is not part of another id
            escaped_chart_id = re.escape(chart_id)
            canvas_pattern_full = rf'<canvas[^>]*id=["\']{escaped_chart_id}(?![a-zA-Z0-9_])["\'][^>]*>'
            canvas_match = re.search(canvas_pattern_full, content, re.IGNORECASE)
            
            if canvas_match:
                canvas_start = canvas_match.start()
                # Check if this canvas is inside an HTML comment
                # Look backwards from canvas start for <!--
                before_canvas = content[:canvas_start]
                last_comment_start = before_canvas.rfind('<!--')
                
                if last_comment_start >= 0:
                    # Found a comment start, check if it's closed before this canvas
                    # Look for --> between the comment start and canvas
                    section_between = content[last_comment_start:canvas_start]
                    if '-->' not in section_between:
                        # Canvas is inside a comment (<!-- ... canvas ... (no closing --> before canvas))
                        logger.debug(f"Chart {chart_id} is in HTML comment, skipping")
                        continue
            
            # Canvas found and not in comment, include it
            canvas_matches.append(chart_id)
        
        logger.info(f"Found {len(canvas_matches)} chart IDs in template (excluding commented ones): {canvas_matches}")
        
        # Find chart titles from HTML structure
        for chart_id in canvas_matches:
            title = None
            
            # Find the position of the canvas element
            canvas_pos = content.find(f'id="{chart_id}"')
            if canvas_pos == -1:
                canvas_pos = content.find(f"id='{chart_id}'")
            
            if canvas_pos > 0:
                # Get the content before the canvas
                before_canvas = content[:canvas_pos]
                
                # Method 1: Look for h3, h4, h5 before the canvas (most common pattern)
                # Search backwards from canvas position
                h_patterns = [
                    r'<h3[^>]*>([^<]+)</h3>',
                    r'<h4[^>]*>([^<]+)</h4>',
                    r'<h5[^>]*>([^<]+)</h5>',
                ]
                
                for pattern in h_patterns:
                    matches = list(re.finditer(pattern, before_canvas))
                    if matches:
                        # Get the last match before canvas (closest to canvas)
                        last_match = matches[-1]
                        # Check if it's reasonably close (within 500 characters)
                        if canvas_pos - last_match.end() < 500:
                            title = last_match.group(1).strip()
                            break
                
                # Method 2: Look for card-title class
                if not title:
                    title_pattern = r'<h[345][^>]*class=["\'][^"\']*card-title[^"\']*["\'][^>]*>([^<]+)</h[345]>'
                    title_match = re.search(title_pattern, before_canvas)
                    if title_match:
                        title = title_match.group(1).strip()
                
                # Method 3: Look for card-header
                if not title:
                    header_pattern = r'<div[^>]*class=["\'][^"\']*card-header[^"\']*["\'][^>]*>([^<]+)</div>'
                    header_match = re.search(header_pattern, before_canvas)
                    if header_match:
                        title = header_match.group(1).strip()
                
                # Method 4: Look for Chart.js title in options
                if not title:
                    # Search for Chart.js title configuration after the canvas
                    after_canvas = content[canvas_pos:canvas_pos + 2000]  # Look 2000 chars ahead
                    chart_title_patterns = [
                        r'title:\s*\{\s*[^}]*text:\s*["\']([^"\']+)["\']',
                        r'text:\s*["\']([^"\']+)["\'].*title',
                        r'charttitle:\s*([^,\}]+)',
                    ]
                    for pattern in chart_title_patterns:
                        title_match = re.search(pattern, after_canvas, re.IGNORECASE)
                        if title_match:
                            title = title_match.group(1).strip().strip('"\'')
                            break
            
            # Fallback to chart_id if no title found
            if not title:
                title = chart_id
            
            # Extract chart type and sample data from JavaScript
            chart_type = None  # Will be extracted, no default yet
            sample_labels = []
            sample_datasets = []
            chart_config = None  # Will be used to store Chart.js config for reuse
            
            logger.info(f"Starting chart extraction for {chart_id}, canvas_pos: {canvas_pos}")
            
            # NEW APPROACH: Find parent div, then find related JavaScript code
            # Step 1: Find the canvas element and its parent div
            if canvas_pos > 0:
                # Find the opening tag of canvas
                canvas_tag_start = content.rfind('<canvas', 0, canvas_pos)
                if canvas_tag_start == -1:
                    canvas_tag_start = content.rfind('<canvas ', 0, canvas_pos)
                
                if canvas_tag_start > 0:
                    # Find the parent div by looking backwards for the nearest opening <div> tag
                    # Look for div tags before the canvas
                    div_pattern = r'<div[^>]*>'
                    div_matches = list(re.finditer(div_pattern, content[:canvas_tag_start], re.IGNORECASE))
                    
                    if div_matches:
                        # Get the last div before canvas (most likely parent)
                        parent_div_match = div_matches[-1]
                        parent_div_start = parent_div_match.start()
                        logger.debug(f"Found potential parent div for {chart_id} at position {parent_div_start}")
                        
                        # Find the closing tag of this div (to get the div's content range)
                        # Count div tags to find matching closing tag
                        div_count = 1
                        search_pos = canvas_tag_start
                        div_end = -1
                        while search_pos < len(content) and div_count > 0:
                            next_open = content.find('<div', search_pos)
                            next_close = content.find('</div>', search_pos)
                            
                            if next_close == -1:
                                break
                            
                            if next_open != -1 and next_open < next_close:
                                div_count += 1
                                search_pos = next_open + 4
                            else:
                                div_count -= 1
                                if div_count == 0:
                                    div_end = next_close
                                    break
                                search_pos = next_close + 6
                        
                        # Now search for JavaScript code that uses this chart_id within script tags
                        # Look for script tags that contain getElementById with this chart_id
                        script_pattern = r'<script[^>]*>(.*?)</script>'
                        script_matches = list(re.finditer(script_pattern, content, re.IGNORECASE | re.DOTALL))
                        
                        for script_match in script_matches:
                            script_content = script_match.group(1)
                            
                            # Check if this script contains getElementById with our chart_id
                            # Use exact match to ensure chart_id is not part of another id
                            escaped_chart_id = re.escape(chart_id)
                            chart_id_pattern = rf'getElementById\s*\(["\']?{escaped_chart_id}(?![a-zA-Z0-9_])["\']?\)'
                            if re.search(chart_id_pattern, script_content, re.IGNORECASE):
                                logger.info(f"Found script block containing getElementById for {chart_id}")
                                
                                # Find the Chart initialization in this script
                                # Look for: new Chart(...) after getElementById
                                get_element_in_script = re.search(chart_id_pattern, script_content, re.IGNORECASE)
                                if get_element_in_script:
                                    # Get content after getElementById
                                    after_getelement = script_content[get_element_in_script.end():]
                                    
                                    # Find Chart initialization
                                    chart_init_patterns = [
                                        r'new\s+Chart\s*\([^,]+,\s*\{',  # new Chart(anything, {
                                        r'const\s+\w+Chart\s*=\s*new\s+Chart\s*\([^,]+,\s*\{',  # const sexChart = new Chart(...)
                                    ]
                                    
                                    for pattern in chart_init_patterns:
                                        chart_init_match = re.search(pattern, after_getelement, re.IGNORECASE | re.DOTALL)
                                        if chart_init_match:
                                            # Extract the Chart config object
                                            chart_start_in_script = chart_init_match.start()
                                            chart_section = after_getelement[chart_start_in_script:]
                                            
                                            # Find the matching closing brace
                                            brace_count = 0
                                            chart_end_in_script = 0
                                            in_string = False
                                            string_char = None
                                            escaped = False
                                            
                                            for i, char in enumerate(chart_section):
                                                if escaped:
                                                    escaped = False
                                                    continue
                                                if char == '\\':
                                                    escaped = True
                                                    continue
                                                if char in ['"', "'"]:
                                                    if not in_string:
                                                        in_string = True
                                                        string_char = char
                                                    elif char == string_char:
                                                        in_string = False
                                                        string_char = None
                                                elif not in_string:
                                                    if char == '{':
                                                        brace_count += 1
                                                    elif char == '}':
                                                        brace_count -= 1
                                                        if brace_count == 0:
                                                            chart_end_in_script = i + 1
                                                            break
                                            
                                            if chart_end_in_script > 0:
                                                chart_config = chart_section[:chart_end_in_script]
                                                logger.info(f"Extracted chart_config for {chart_id} from script block, length: {len(chart_config)}")
                                                logger.debug(f"Chart config preview: {chart_config[:500]}")
                                                break
                                    
                                    if chart_config:
                                        break
                
                # Fallback: If we didn't find via parent div approach, use the old method
                if not chart_config:
                    logger.debug(f"Parent div approach didn't work for {chart_id}, trying fallback method")
                    # Use the old method as fallback
                    search_start = max(0, canvas_pos - 500)
                    search_end = min(len(content), canvas_pos + 10000)
                    search_content = content[search_start:search_end]
                    
                    # Use exact match to ensure chart_id is not part of another id
                    escaped_chart_id = re.escape(chart_id)
                    get_element_pattern = rf'getElementById\s*\(["\']?{escaped_chart_id}(?![a-zA-Z0-9_])["\']?\)'
                    get_element_match = re.search(get_element_pattern, search_content, re.IGNORECASE)
                    
                    if get_element_match:
                        match_pos_in_search = get_element_match.end()
                        chart_section_start = search_start + match_pos_in_search
                        chart_section_end = min(len(content), chart_section_start + 5000)
                        chart_section = content[chart_section_start:chart_section_end]
                        
                        chart_init_patterns = [
                            r'new\s+Chart\s*\([^,]+,\s*\{',
                            r'const\s+\w+Chart\s*=\s*new\s+Chart\s*\([^,]+,\s*\{',
                        ]
                        chart_init_match = None
                        for pattern in chart_init_patterns:
                            chart_init_match = re.search(pattern, chart_section, re.IGNORECASE | re.DOTALL)
                            if chart_init_match:
                                break
                        
                        if chart_init_match:
                            chart_start = chart_init_match.start()
                            brace_count = 0
                            chart_end = chart_start
                            in_string = False
                            string_char = None
                            escaped = False
                            for i, char in enumerate(chart_section[chart_start:], start=chart_start):
                                if escaped:
                                    escaped = False
                                    continue
                                if char == '\\':
                                    escaped = True
                                    continue
                                if char in ['"', "'"]:
                                    if not in_string:
                                        in_string = True
                                        string_char = char
                                    elif char == string_char:
                                        in_string = False
                                        string_char = None
                                elif not in_string:
                                    if char == '{':
                                        brace_count += 1
                                    elif char == '}':
                                        brace_count -= 1
                                        if brace_count == 0:
                                            chart_end = i + 1
                                            break
                            if chart_end > chart_start:
                                chart_config = chart_section[chart_start:chart_end]
                                logger.info(f"Extracted chart_config for {chart_id} using fallback method, length: {len(chart_config)}")
                
                # Extract type from chart_config
                if chart_config:
                    # Try multiple patterns to find chart type - prioritize specific chart types
                    type_patterns = [
                        r"type\s*:\s*['\"](pie|line|bar|doughnut|radar|polarArea|area)['\"]",  # type: 'pie' - specific types first
                        r"type\s*:\s*(pie|line|bar|doughnut|radar|polarArea|area)\s*[,}]",  # type: pie, or type: pie} - without quotes
                        r"['\"]type['\"]\s*:\s*['\"](pie|line|bar|doughnut|radar|polarArea|area)['\"]",  # "type": "pie"
                        r"type\s*:\s*['\"]([^'\"]+)['\"]",  # type: 'anything' - fallback
                        r"type\s*:\s*([a-zA-Z]+)",  # type: anything (without quotes) - fallback
                    ]
                    type_match = None
                    for pattern in type_patterns:
                        type_match = re.search(pattern, chart_config, re.IGNORECASE)
                        if type_match:
                            chart_type = type_match.group(1).lower().strip()
                            # Validate that it's a known chart type
                            valid_types = ['pie', 'line', 'bar', 'doughnut', 'radar', 'polararea', 'area']
                            if chart_type in valid_types:
                                # Check if this is a line chart with fill: true (which means it's an area chart)
                                if chart_type == 'line':
                                    # Look for fill: true in the chart config
                                    fill_pattern = r'fill\s*:\s*true'
                                    if re.search(fill_pattern, chart_config, re.IGNORECASE):
                                        chart_type = 'area'
                                        logger.info(f"Detected area chart (line with fill: true) for {chart_id}")
                                
                                logger.info(f"Extracted chart type '{chart_type}' for {chart_id} from JavaScript using pattern: {pattern}")
                                logger.debug(f"Chart config snippet: {chart_config[:300]}")
                                break
                            else:
                                logger.warning(f"Found invalid chart type '{chart_type}' for {chart_id}, continuing search...")
                                type_match = None
                    
                    if not type_match:
                        logger.warning(f"Could not find valid 'type' in chart_config for {chart_id}. Config preview: {chart_config[:300]}")
                        logger.warning(f"Full chart_config length: {len(chart_config)}")
                else:
                    logger.warning(f"Could not find chart_config for {chart_id}. canvas_pos={canvas_pos}")
                    # Try to find type directly in the content around canvas
                    if canvas_pos > 0:
                        # Look for type: 'pie' pattern in a wider range around canvas
                        search_start = max(0, canvas_pos - 2000)
                        search_end = min(len(content), canvas_pos + 8000)  # Increased range
                        search_content = content[search_start:search_end]
                        
                        # Look for Chart initialization with this chart_id
                        # Use exact match to ensure chart_id is not part of another id
                        escaped_chart_id = re.escape(chart_id)
                        chart_id_pattern = rf'getElementById\s*\(["\']?{escaped_chart_id}(?![a-zA-Z0-9_])["\']?\)'
                        chart_id_match = re.search(chart_id_pattern, search_content, re.IGNORECASE)
                        if chart_id_match:
                            # Find new Chart after getElementById - look in a larger window
                            after_getelement = search_content[chart_id_match.end():]
                            # Look for new Chart within 3000 chars after getElementById
                            chart_init_match = re.search(r'new\s+Chart\s*\([^,]+,\s*\{', after_getelement[:3000], re.IGNORECASE | re.DOTALL)
                            if chart_init_match:
                                # Extract type from the Chart config
                                chart_config_section = after_getelement[chart_init_match.start():chart_init_match.start() + 2000]
                                type_patterns = [
                                    r"type\s*:\s*['\"]([^'\"]+)['\"]",  # type: 'pie'
                                    r"type\s*:\s*([a-zA-Z]+)",  # type: pie (without quotes)
                                ]
                                for pattern in type_patterns:
                                    type_match = re.search(pattern, chart_config_section, re.IGNORECASE)
                                    if type_match:
                                        chart_type = type_match.group(1).lower().strip()
                                        # Check if this is a line chart with fill: true (which means it's an area chart)
                                        if chart_type == 'line':
                                            fill_pattern = r'fill\s*:\s*true'
                                            if re.search(fill_pattern, chart_config_section, re.IGNORECASE):
                                                chart_type = 'area'
                                                logger.info(f"Detected area chart (line with fill: true) for {chart_id}")
                                        logger.info(f"Extracted chart type '{chart_type}' for {chart_id} using direct search after getElementById")
                                        break
            
            # SECOND: Try to get actual data directly from dashboard_data
            # This is a general approach that works for all dashboards
            if dashboard_data:
                # Try to extract variable names from HTML/JS and match them with dashboard_data
                # Look for Jinja variables in the HTML around this canvas
                if canvas_pos > 0:
                    # Get context around canvas (before and after)
                    context_start = max(0, canvas_pos - 1000)
                    context_end = min(len(content), canvas_pos + 2000)
                    chart_context = content[context_start:context_end]
                    
                    # Find all Jinja variables in this context ({{ variable|tojson }})
                    jinja_vars = re.findall(r'\{\{\s*([^|}\s]+)', chart_context)
                    
                    # Try to match these variables with dashboard_data keys
                    for var_name in jinja_vars:
                        var_name = var_name.strip()
                        if not var_name:
                            continue
                        
                        # Pattern 1: Direct match
                        if var_name in dashboard_data:
                            data_obj = dashboard_data[var_name]
                            if isinstance(data_obj, dict):
                                if 'labels' in data_obj and not sample_labels:
                                    sample_labels = data_obj['labels']
                                if 'counts' in data_obj and not sample_datasets:
                                    counts = data_obj['counts']
                                    if counts:
                                        if chart_type in ['pie', 'doughnut']:
                                            colors = ['#36A2EB', '#FF6384', '#FFCE56', '#4BC0C0', '#9966FF', '#FF9F40', '#C9CBCF']
                                            sample_datasets = [{
                                                'data': counts,
                                                'backgroundColor': colors[:len(counts)]
                                            }]
                                        else:
                                            sample_datasets = [{
                                                'label': 'تعداد',
                                                'data': counts,
                                                'backgroundColor': 'rgba(54, 162, 235, 0.2)',
                                                'borderColor': 'rgba(54, 162, 235, 1)',
                                                'borderWidth': 1
                                            }]
                            elif isinstance(data_obj, list) and not sample_labels:
                                sample_labels = data_obj
                        
                        # Pattern 2: var_name_labels -> var_name_data['labels']
                        # Example: sex_labels -> sex_data['labels']
                        elif var_name.endswith('_labels'):
                            base = var_name.replace('_labels', '')
                            # Try exact match first: sex_labels -> sex_data
                            data_key = f'{base}_data'
                            if data_key in dashboard_data and isinstance(dashboard_data[data_key], dict):
                                if 'labels' in dashboard_data[data_key] and not sample_labels:
                                    sample_labels = dashboard_data[data_key]['labels']
                                    logger.info(f"Found labels for {chart_id} from {data_key}: {len(sample_labels)} labels")
                            else:
                                # Try partial match
                                for key in dashboard_data.keys():
                                    if key.startswith(base) and isinstance(dashboard_data[key], dict):
                                        if 'labels' in dashboard_data[key] and not sample_labels:
                                            sample_labels = dashboard_data[key]['labels']
                                            logger.info(f"Found labels for {chart_id} from {key}: {len(sample_labels)} labels")
                                            break
                        
                        # Pattern 3: var_name_counts -> var_name_data['counts']
                        # Example: sex_counts -> sex_data['counts']
                        elif var_name.endswith('_counts'):
                            base = var_name.replace('_counts', '')
                            # Try exact match first: sex_counts -> sex_data
                            data_key = f'{base}_data'
                            if data_key in dashboard_data and isinstance(dashboard_data[data_key], dict):
                                if 'counts' in dashboard_data[data_key] and not sample_datasets:
                                    counts = dashboard_data[data_key]['counts']
                                    if counts:
                                        if chart_type in ['pie', 'doughnut']:
                                            colors = ['#36A2EB', '#FF6384', '#FFCE56', '#4BC0C0', '#9966FF', '#FF9F40', '#C9CBCF']
                                            sample_datasets = [{
                                                'data': counts,
                                                'backgroundColor': colors[:len(counts)]
                                            }]
                                        else:
                                            sample_datasets = [{
                                                'label': 'تعداد',
                                                'data': counts,
                                                'backgroundColor': 'rgba(54, 162, 235, 0.2)',
                                                'borderColor': 'rgba(54, 162, 235, 1)',
                                                'borderWidth': 1
                                            }]
                                        logger.info(f"Found counts for {chart_id} from {data_key}: {len(counts)} values, chart_type={chart_type}")
                            else:
                                # Try partial match
                                for key in dashboard_data.keys():
                                    if key.startswith(base) and isinstance(dashboard_data[key], dict):
                                        if 'counts' in dashboard_data[key] and not sample_datasets:
                                            counts = dashboard_data[key]['counts']
                                            if counts:
                                                if chart_type in ['pie', 'doughnut']:
                                                    colors = ['#36A2EB', '#FF6384', '#FFCE56', '#4BC0C0', '#9966FF', '#FF9F40', '#C9CBCF']
                                                    sample_datasets = [{
                                                        'data': counts,
                                                        'backgroundColor': colors[:len(counts)]
                                                    }]
                                                else:
                                                    sample_datasets = [{
                                                        'label': 'تعداد',
                                                        'data': counts,
                                                        'backgroundColor': 'rgba(54, 162, 235, 0.2)',
                                                        'borderColor': 'rgba(54, 162, 235, 1)',
                                                        'borderWidth': 1
                                                    }]
                                                logger.info(f"Found counts for {chart_id} from {key}: {len(counts)} values, chart_type={chart_type}")
                                                break
                    
                    # Special handling for multi-dataset charts (like markaz with male_counts and female_counts)
                    # Check if we have both male_counts and female_counts in context
                    if 'male_counts' in jinja_vars and 'female_counts' in jinja_vars:
                        # Look for a data key that contains both
                        for key in dashboard_data.keys():
                            if isinstance(dashboard_data[key], dict):
                                if 'male_counts' in dashboard_data[key] and 'female_counts' in dashboard_data[key]:
                                    markaz_data = dashboard_data[key]
                                    if 'labels' in markaz_data and not sample_labels:
                                        sample_labels = markaz_data['labels']
                                    if not sample_datasets:
                                        sample_datasets = [
                                            {
                                                'label': 'مرد',
                                                'data': markaz_data['male_counts'],
                                                'backgroundColor': 'rgba(54, 162, 235, 0.7)',
                                                'borderColor': 'rgba(54, 162, 235, 1)',
                                                'borderWidth': 2
                                            },
                                            {
                                                'label': 'زن',
                                                'data': markaz_data['female_counts'],
                                                'backgroundColor': 'rgba(255, 99, 132, 0.7)',
                                                'borderColor': 'rgba(255, 99, 132, 1)',
                                                'borderWidth': 2
                                            }
                                        ]
                                    break
                    
                    # Special handling for nested pie charts (like multiLevelPieChart)
                    if 'inner_labels' in jinja_vars or 'outer_labels' in jinja_vars:
                        for key in dashboard_data.keys():
                            if isinstance(dashboard_data[key], dict):
                                if 'inner_labels' in dashboard_data[key] and 'outer_labels' in dashboard_data[key]:
                                    nested_data = dashboard_data[key]
                                    if 'outer_labels' in nested_data and not sample_labels:
                                        sample_labels = nested_data['outer_labels']
                                    if 'outer_data' in nested_data and 'inner_data' in nested_data and not sample_datasets:
                                        sample_datasets = [
                                            {
                                                'label': 'جنسیت در هر نوع استخدام',
                                                'data': nested_data['outer_data'],
                                                'backgroundColor': [
                                                    '#ff6384', '#36a2eb', '#ffcd56', '#4bc0c0', '#9966ff',
                                                    '#ff9f40', '#c9cbcf', '#84ff63', '#eb36a2', '#9fa8da'
                                                ],
                                                'borderWidth': 1
                                            },
                                            {
                                                'label': 'نوع استخدام',
                                                'data': nested_data['inner_data'],
                                                'backgroundColor': [
                                                    '#b71c1c', '#0d47a1', '#33691e', '#e65100', '#4a148c',
                                                    '#263238', '#827717', '#1b5e20', '#01579b'
                                                ],
                                                'borderWidth': 1
                                            }
                                        ]
                                        chart_type = 'doughnut'
                                    break
                
                # If we found actual data, log it
                if sample_labels or sample_datasets:
                    logger.info(f"Found actual data for {chart_id}: labels={len(sample_labels) if sample_labels else 0}, datasets={len(sample_datasets) if sample_datasets else 0}")
            
            # THIRD: If we still don't have data, try to extract from JavaScript
            # Reuse chart_config if we already found it above (for type extraction)
            if (not sample_labels or not sample_datasets) and canvas_pos > 0:
                # If chart_config was not found in the first step, try to find it now
                if not chart_config:
                    # Look for Chart.js configuration after the canvas
                    after_canvas = content[canvas_pos:canvas_pos + 5000]  # Look 5000 chars ahead
                    
                    # Find the Chart.js initialization for this canvas
                    # Use exact match to ensure chart_id is not part of another id
                    escaped_chart_id = re.escape(chart_id)
                    get_element_pattern = rf'getElementById\s*\(["\']?{escaped_chart_id}(?![a-zA-Z0-9_])["\']?\)'
                    get_element_match = re.search(get_element_pattern, after_canvas, re.IGNORECASE)
                    
                    chart_config = None
                    if get_element_match:
                        # Get content after getElementById call (should contain Chart initialization)
                        chart_section_start = get_element_match.end()
                        chart_section = after_canvas[chart_section_start:chart_section_start + 3000]  # Look 3000 chars ahead
                        
                        # Find Chart initialization after getElementById
                        chart_init_match = re.search(r'new\s+Chart\s*\([^)]*ctx[^)]*,\s*\{', chart_section, re.IGNORECASE | re.DOTALL)
                        if chart_init_match:
                            # Get the full Chart configuration (from new Chart to closing brace)
                            chart_start = chart_init_match.start()
                            # Find the matching closing brace for the Chart config object
                            brace_count = 0
                            chart_end = chart_start
                            in_string = False
                            string_char = None
                            for i, char in enumerate(chart_section[chart_start:], start=chart_start):
                                if char in ['"', "'"] and (i == chart_start or chart_section[i-1] != '\\'):
                                    if not in_string:
                                        in_string = True
                                        string_char = char
                                    elif char == string_char:
                                        in_string = False
                                        string_char = None
                                elif not in_string:
                                    if char == '{':
                                        brace_count += 1
                                    elif char == '}':
                                        brace_count -= 1
                                        if brace_count == 0:
                                            chart_end = i + 1
                                            break
                            if chart_end > chart_start:
                                chart_config = chart_section[chart_start:chart_end]
                
                if chart_config:
                    # Note: chart_type was already extracted in the FIRST step above
                    # Extract labels (try to find labels array)
                    labels_patterns = [
                        r"labels:\s*(\[[^\]]+\])",
                        r"labels:\s*(\{[^}]+\})",
                        r"labels:\s*([^,\}]+)",
                    ]
                    for pattern in labels_patterns:
                        labels_match = re.search(pattern, chart_config, re.IGNORECASE)
                        if labels_match:
                            try:
                                # Try to parse as JSON or extract values
                                labels_str = labels_match.group(1)
                                # If it's a Jinja template variable, try to get actual data from dashboard
                                if '|' in labels_str or '{{' in labels_str:
                                    # Extract variable name (e.g., {{ sex_labels|tojson }} -> sex_labels)
                                    var_match = re.search(r'\{\{\s*([^|}\s]+)', labels_str)
                                    if var_match and dashboard_data:
                                        var_name = var_match.group(1).strip()
                                        # Try to get actual data from dashboard_data
                                        # Pattern 1: Direct match (e.g., sex_labels in dashboard_data)
                                        if var_name in dashboard_data:
                                            actual_data = dashboard_data[var_name]
                                            if isinstance(actual_data, dict) and 'labels' in actual_data:
                                                sample_labels = actual_data['labels']
                                            elif isinstance(actual_data, list):
                                                sample_labels = actual_data
                                        # Pattern 2: sex_labels -> sex_data['labels'] (common pattern)
                                        # In dashboard_data, we have sex_data, not sex_labels
                                        elif var_name.endswith('_labels') and dashboard_data:
                                            base_name = var_name.replace('_labels', '')
                                            # Try sex_data, sexData, etc.
                                            for data_key in [f'{base_name}_data', f'{base_name}Data', f'{base_name}']:
                                                if data_key in dashboard_data and isinstance(dashboard_data[data_key], dict):
                                                    labels = dashboard_data[data_key].get('labels', [])
                                                    if labels:
                                                        sample_labels = labels
                                                        break
                                        # Pattern 3: Check if it's a direct key in dashboard_data
                                        elif var_name in dashboard_data:
                                            if isinstance(dashboard_data[var_name], list):
                                                sample_labels = dashboard_data[var_name]
                                        # Pattern 4: If var_name is like 'sex_labels', check for 'sex_data' in dashboard_data
                                        if not sample_labels and var_name.endswith('_labels'):
                                            base = var_name.replace('_labels', '')
                                            # Check for base_data (e.g., sex_data) in dashboard_data
                                            for key in dashboard_data.keys():
                                                if key.startswith(base) and isinstance(dashboard_data[key], dict):
                                                    labels = dashboard_data[key].get('labels', [])
                                                    if labels:
                                                        sample_labels = labels
                                                        break
                                    # Fallback to sample if no actual data found
                                    if not sample_labels:
                                        sample_labels = ['فروردین', 'اردیبهشت', 'خرداد', 'تیر', 'مرداد']
                                else:
                                    # Try to parse as JSON
                                    import json
                                    sample_labels = json.loads(labels_str)
                            except Exception as e:
                                logger.warning(f"Error extracting labels for {chart_id}: {e}")
                                sample_labels = ['فروردین', 'اردیبهشت', 'خرداد', 'تیر', 'مرداد']
                            break
                    
                    # Extract datasets (try to find data array) - only if we don't have actual data yet
                    if not sample_datasets:
                        data_patterns = [
                            r"data:\s*(\[[^\]]+\])",
                            r"data:\s*(\{[^}]+\})",
                        ]
                        for pattern in data_patterns:
                            data_match = re.search(pattern, chart_config, re.IGNORECASE)
                            if data_match:
                                try:
                                    data_str = data_match.group(1)
                                    # If it's a Jinja template variable, try to get actual data from dashboard
                                    if '|' in data_str or '{{' in data_str:
                                        # Extract variable name (e.g., {{ sex_counts|tojson }} -> sex_counts)
                                        var_match = re.search(r'\{\{\s*([^|}\s]+)', data_str)
                                        if var_match and dashboard_data:
                                            var_name = var_match.group(1).strip()
                                            # Try to get actual data from dashboard_data
                                            # Pattern 1: Direct match (e.g., sex_counts in dashboard_data)
                                            if var_name in dashboard_data:
                                                actual_data = dashboard_data[var_name]
                                                if isinstance(actual_data, list):
                                                    # Determine colors based on chart type
                                                    if chart_type in ['pie', 'doughnut']:
                                                        colors = ['#36A2EB', '#FF6384', '#FFCE56', '#4BC0C0', '#9966FF', '#FF9F40', '#C9CBCF']
                                                        sample_datasets = [{
                                                            'data': actual_data,
                                                            'backgroundColor': colors[:len(actual_data)]
                                                        }]
                                                    else:
                                                        sample_datasets = [{
                                                            'data': actual_data,
                                                            'backgroundColor': 'rgba(54, 162, 235, 0.2)',
                                                            'borderColor': 'rgba(54, 162, 235, 1)'
                                                        }]
                                            # Pattern 2: sex_counts -> sex_data['counts'] (common pattern)
                                            # In dashboard_data, we have sex_data, not sex_counts
                                            elif var_name.endswith('_counts') and dashboard_data:
                                                base_name = var_name.replace('_counts', '')
                                                # Try sex_data, sexData, etc.
                                                for data_key in [f'{base_name}_data', f'{base_name}Data', f'{base_name}']:
                                                    if data_key in dashboard_data and isinstance(dashboard_data[data_key], dict):
                                                        counts = dashboard_data[data_key].get('counts', [])
                                                        if counts:
                                                            if chart_type in ['pie', 'doughnut']:
                                                                colors = ['#36A2EB', '#FF6384', '#FFCE56', '#4BC0C0', '#9966FF', '#FF9F40', '#C9CBCF']
                                                                sample_datasets = [{
                                                                    'data': counts,
                                                                    'backgroundColor': colors[:len(counts)]
                                                                }]
                                                            else:
                                                                sample_datasets = [{
                                                                    'data': counts,
                                                                    'backgroundColor': 'rgba(54, 162, 235, 0.2)',
                                                                    'borderColor': 'rgba(54, 162, 235, 1)'
                                                                }]
                                                            break
                                            # Pattern 3: If var_name is like 'sex_counts', check for 'sex_data' in dashboard_data
                                            if not sample_datasets and var_name.endswith('_counts'):
                                                base = var_name.replace('_counts', '')
                                                # Check for base_data (e.g., sex_data) in dashboard_data
                                                for key in dashboard_data.keys():
                                                    if key.startswith(base) and isinstance(dashboard_data[key], dict):
                                                        counts = dashboard_data[key].get('counts', [])
                                                        if counts:
                                                            if chart_type in ['pie', 'doughnut']:
                                                                colors = ['#36A2EB', '#FF6384', '#FFCE56', '#4BC0C0', '#9966FF', '#FF9F40', '#C9CBCF']
                                                                sample_datasets = [{
                                                                    'data': counts,
                                                                    'backgroundColor': colors[:len(counts)]
                                                                }]
                                                            else:
                                                                sample_datasets = [{
                                                                    'data': counts,
                                                                    'backgroundColor': 'rgba(54, 162, 235, 0.2)',
                                                                    'borderColor': 'rgba(54, 162, 235, 1)'
                                                                }]
                                                            break
                                        # Fallback to sample if no actual data found
                                        if not sample_datasets:
                                            if chart_type in ['pie', 'doughnut']:
                                                sample_datasets = [{'data': [330, 649], 'backgroundColor': ['#36A2EB', '#FF6384']}]
                                            else:
                                                sample_datasets = [{'data': [12, 19, 3, 5, 2], 'backgroundColor': 'rgba(54, 162, 235, 0.2)'}]
                                    else:
                                        import json
                                        data = json.loads(data_str)
                                        if isinstance(data, list):
                                            sample_datasets = [{'data': data}]
                                except Exception as e:
                                    logger.warning(f"Error extracting data for {chart_id}: {e}")
                                    pass
                                break
            
            # Set default chart_type if not extracted - but only as last resort
            if not chart_type:
                # Try one more aggressive search: look for 'type:' anywhere near the canvas
                if canvas_pos > 0:
                    aggressive_start = max(0, canvas_pos - 5000)
                    aggressive_end = min(len(content), canvas_pos + 10000)
                    aggressive_content = content[aggressive_start:aggressive_end]
                    
                    # Look for getElementById with chart_id
                    # Use exact match to ensure chart_id is not part of another id
                    escaped_chart_id = re.escape(chart_id)
                    chart_id_in_content = rf'getElementById\s*\(["\']?{escaped_chart_id}(?![a-zA-Z0-9_])["\']?\)'
                    if re.search(chart_id_in_content, aggressive_content, re.IGNORECASE):
                        # Find the first occurrence of 'type:' after getElementById
                        # This is a very permissive pattern
                        type_patterns_aggressive = [
                            r"type\s*:\s*['\"](pie|line|bar|doughnut|radar|polarArea|area)['\"]",  # type: 'pie'
                            r"type\s*:\s*(pie|line|bar|doughnut|radar|polarArea|area)\s*[,}]",  # type: pie, or type: pie}
                            r"['\"]type['\"]\s*:\s*['\"](pie|line|bar|doughnut|radar|polarArea|area)['\"]",  # "type": "pie"
                        ]
                        for pattern in type_patterns_aggressive:
                            match = re.search(pattern, aggressive_content, re.IGNORECASE)
                            if match:
                                chart_type = match.group(1).lower().strip()
                                # Check if this is a line chart with fill: true (which means it's an area chart)
                                if chart_type == 'line':
                                    fill_pattern = r'fill\s*:\s*true'
                                    if re.search(fill_pattern, aggressive_content, re.IGNORECASE):
                                        chart_type = 'area'
                                        logger.info(f"Detected area chart (line with fill: true) for {chart_id}")
                                logger.info(f"Extracted chart type '{chart_type}' for {chart_id} using aggressive search with pattern: {pattern}")
                                break
                
                if not chart_type:
                    logger.error(f"CRITICAL: Chart type not extracted for {chart_id} after all attempts! Using default 'line'. Canvas pos: {canvas_pos}")
                    logger.error(f"Content around canvas (first 500 chars): {content[max(0, canvas_pos-250):canvas_pos+250]}")
                    chart_type = 'line'
            
            # If no sample data extracted, use defaults based on chart type
            if not sample_labels:
                if chart_type in ['pie', 'doughnut']:
                    sample_labels = ['مرد', 'زن']
                else:
                    sample_labels = ['فروردین', 'اردیبهشت', 'خرداد', 'تیر', 'مرداد']
            if not sample_datasets:
                if chart_type in ['pie', 'doughnut']:
                    sample_datasets = [{'data': [330, 649], 'backgroundColor': ['#36A2EB', '#FF6384', '#FFCE56', '#4BC0C0', '#9966FF']}]
                elif chart_type == 'bar':
                    sample_datasets = [{'data': [12, 19, 3, 5, 2], 'backgroundColor': 'rgba(255, 159, 64, 0.6)', 'borderColor': 'rgba(255, 159, 64, 1)'}]
                else:
                    sample_datasets = [{'data': [12, 19, 3, 5, 2], 'backgroundColor': 'rgba(54, 162, 235, 0.2)', 'borderColor': 'rgba(54, 162, 235, 1)'}]
            
            # Extract chart settings from HTML (not from database)
            # Read settings directly from HTML/JavaScript in the template
            show_labels = True  # default
            show_legend = True  # default
            allow_export = True  # default
            is_visible = True  # default
            
            # Try to extract these settings from HTML/JavaScript
            if canvas_pos > 0:
                after_canvas = content[canvas_pos:canvas_pos + 5000]
                
                # Extract show_labels (datalabels.display)
                datalabels_pattern = r'datalabels\s*:\s*\{[^}]*display\s*:\s*(true|false)'
                datalabels_match = re.search(datalabels_pattern, after_canvas, re.IGNORECASE | re.DOTALL)
                if datalabels_match:
                    show_labels = datalabels_match.group(1).lower() == 'true'
                
                # Extract show_legend (legend.display)
                legend_pattern = r'legend\s*:\s*\{[^}]*display\s*:\s*(true|false)'
                legend_match = re.search(legend_pattern, after_canvas, re.IGNORECASE | re.DOTALL)
                if legend_match:
                    show_legend = legend_match.group(1).lower() == 'true'
            
            # Determine display_order from HTML position (order of appearance in HTML)
            # Charts are already in order of appearance in HTML (canvas_matches)
            display_order = len(charts)
            
            # Check if chart is visible (not in commented section)
            # We already filtered out commented charts, so all found charts are visible
            is_visible = True
            
            # Log extracted chart info for debugging
            logger.info(f"Chart {chart_id}: type={chart_type}, labels={len(sample_labels) if sample_labels else 0}, datasets={len(sample_datasets) if sample_datasets else 0}, has_actual_data={bool(dashboard_data)}")
            
            # Create config dict from HTML (not from database)
            # color_palette will be loaded from database after all charts are created
            charts.append({
                'id': None,
                'template_name': template_name,
                'chart_id': chart_id,
                'title': title,  # From HTML
                'display_order': display_order,  # Based on HTML order
                'chart_type': chart_type,  # Extracted from HTML/JS
                'show_labels': show_labels,  # Extracted from HTML/JS
                'show_legend': show_legend,  # Extracted from HTML/JS
                'allow_export': allow_export,  # Default
                'is_visible': is_visible,  # True (already filtered commented charts)
                'color_palette': 'default',  # Will be updated from database
                'chart_options': {
                    'sample_labels': sample_labels,
                    'sample_datasets': sample_datasets
                }
            })
        
        # Sort by display_order
        charts.sort(key=lambda x: x.get('display_order', 0))
        
        # Load color_palette from database for each chart
        try:
            db_configs = ChartConfig.query.filter_by(template_name=template_name).all()
            db_configs_dict = {config.chart_id: config for config in db_configs}
            logger.info(f"Loading color_palette for {len(charts)} charts from {len(db_configs)} configs")
            for chart in charts:
                chart_id = chart.get('chart_id')
                if chart_id in db_configs_dict:
                    db_config = db_configs_dict[chart_id]
                    chart['color_palette'] = db_config.color_palette or 'default'
                    logger.info(f"Chart {chart_id}: color_palette={chart['color_palette']} (from DB)")
                else:
                    chart['color_palette'] = 'default'
                    logger.info(f"Chart {chart_id}: color_palette=default (not in DB)")
        except Exception as e:
            logger.warning(f"Error loading color_palette from database: {e}")
            # Set default for all charts if error
            for chart in charts:
                chart['color_palette'] = 'default'
                logger.warning(f"Chart {chart.get('chart_id')}: color_palette=default (error fallback)")
        
        # Extract tables from HTML
        tables = []
        import re
        
        try:
            try:
                from bs4 import BeautifulSoup
            except ImportError:
                logger.warning("BeautifulSoup4 not installed. Skipping table extraction.")
                BeautifulSoup = None
            
            if BeautifulSoup:
                soup = BeautifulSoup(content, 'html.parser')
                # Find all table elements (excluding those in HTML comments)
                all_tables = soup.find_all('table')
            else:
                all_tables = []
            
            for idx, table in enumerate(all_tables):
                # Check if table is in a comment
                if table.find_parent('comment'):
                    continue
                
                table_id = table.get('id', f'table_{idx}')
                table_class = ' '.join(table.get('class', []))
                
                # Find table title (look for h3, h4, h5, or caption before table)
                title = None
                # Look for caption
                caption = table.find('caption')
                if caption:
                    title = caption.get_text(strip=True)
                else:
                    # Look for heading before table
                    prev_sibling = table.find_previous_sibling(['h3', 'h4', 'h5', 'h6'])
                    if prev_sibling:
                        title = prev_sibling.get_text(strip=True)
                    else:
                        # Look in parent div/card
                        parent = table.find_parent(['div', 'section', 'article'])
                        if parent:
                            heading = parent.find(['h3', 'h4', 'h5', 'h6'])
                            if heading:
                                title = heading.get_text(strip=True)
                
                if not title:
                    title = f'جدول {idx + 1}'
                
                # Extract table structure
                headers = []
                rows_data = []
                
                thead = table.find('thead')
                if thead:
                    header_row = thead.find('tr')
                    if header_row:
                        headers = [th.get_text(strip=True) for th in header_row.find_all(['th', 'td'])]
                
                tbody = table.find('tbody')
                if tbody:
                    for tr in tbody.find_all('tr'):
                        row_data = [td.get_text(strip=True) for td in tr.find_all(['td', 'th'])]
                        if row_data:
                            rows_data.append(row_data)
                
                # If no tbody, check all rows
                if not rows_data:
                    for tr in table.find_all('tr'):
                        row_data = [td.get_text(strip=True) for td in tr.find_all(['td', 'th'])]
                        if row_data:
                            rows_data.append(row_data)
                
                # Try to get actual table data from dashboard_data
                table_data = None
                if dashboard_data:
                    # Look for Jinja variables in table rows
                    table_html = str(table)
                    jinja_vars = re.findall(r'\{\{\s*([^|}\s]+)', table_html)
                    
                    # Try to match with dashboard_data
                    for var_name in jinja_vars:
                        var_name = var_name.strip()
                        if var_name in dashboard_data:
                            data_obj = dashboard_data[var_name]
                            if isinstance(data_obj, (list, dict)):
                                table_data = data_obj
                                break
                
                tables.append({
                    'table_id': table_id,
                    'title': title,
                    'headers': headers,
                    'rows': rows_data[:10] if rows_data else [],  # Limit preview rows
                    'total_rows': len(rows_data) if rows_data else 0,
                    'table_data': table_data,  # Actual data from dashboard
                    'display_order': len(charts) + idx,  # Place after charts
                    'is_visible': True,
                    'allow_excel_export': True
                })
        except Exception as e:
            logger.error(f"Error extracting tables: {e}", exc_info=True)
            tables = []  # Ensure tables is always a list
        
        # Check if there are any charts or tables
        has_elements = len(charts) > 0 or len(tables) > 0
        
        logger.info(f"Template {template_name}: Found {len(charts)} charts and {len(tables)} tables")
        
        return jsonify({
            'success': True,
            'charts': charts,
            'tables': tables,
            'has_elements': has_elements
        })
    except Exception as e:
        logger.error(f"Error in dashboard_template_charts: {e}", exc_info=True)
        return jsonify({'success': False, 'message': f'خطا: {str(e)}'}), 500


@admin_bp.route('/dashboards/templates/<template_name>/save-settings', methods=['POST'])
@login_required
@admin_required
def dashboard_template_save_settings(template_name):
    """Save chart and table settings for a template"""
    try:
        log_action('save_all_settings', 'template', template_name)
    except Exception as e:
        logger.warning(f"Error logging action: {e}")
    
    try:
        # Security check
        if not template_name.endswith('.html') or '..' in template_name or '/' in template_name:
            return jsonify({'success': False, 'message': 'نام فایل نامعتبر است'}), 400
        
        # Get template path
        base_dir = Path(__file__).parent.parent
        template_path = base_dir / 'templates' / 'dashboards' / template_name
        
        if not template_path.exists():
            return jsonify({'success': False, 'message': 'تمپلیت یافت نشد'}), 404
        
        # Get data from request
        if not request.is_json:
            return jsonify({'success': False, 'message': 'درخواست باید JSON باشد'}), 400
        
        data = request.get_json()
        charts = data.get('charts', [])
        tables = data.get('tables', [])
        
        logger.info(f"Received save request for template {template_name}: {len(charts)} charts, {len(tables)} tables")
        
        # Create backup before making changes (same as charts endpoint)
        next_version = None
        try:
            # Read current template content
            with open(template_path, 'r', encoding='utf-8') as f:
                current_content = f.read()
            
            # Get current chart configs
            current_chart_configs = []
            try:
                configs = ChartConfig.query.filter_by(template_name=template_name).all()
                current_chart_configs = [config.to_dict() for config in configs]
            except Exception as e:
                logger.warning(f"Error getting current chart configs: {e}")
            
            # Get next version number
            try:
                max_version = db.session.query(func.max(TemplateVersion.version_number)).filter_by(
                    template_name=template_name
                ).scalar() or 0
                next_version = max_version + 1
            except Exception as e:
                logger.warning(f"Error getting max version number: {e}")
                next_version = 1
            
            # Keep only last 50 versions
            if next_version and next_version > 50:
                try:
                    versions_to_delete = TemplateVersion.query.filter_by(
                        template_name=template_name
                    ).order_by(TemplateVersion.version_number.asc()).limit(next_version - 50).all()
                    for version in versions_to_delete:
                        db.session.delete(version)
                except Exception as e:
                    logger.warning(f"Error deleting old versions: {e}")
            
            # Create version backup
            if next_version:
                try:
                    version = TemplateVersion(
                        template_name=template_name,
                        version_number=next_version,
                        template_content=current_content,
                        chart_configs=current_chart_configs,
                        created_by=current_user.id,
                        description=f'ذخیره خودکار قبل از اعمال تغییرات - نسخه {next_version}'
                    )
                    db.session.add(version)
                    db.session.flush()
                    logger.info(f"Created template version {next_version} for {template_name}")
                except Exception as e:
                    logger.error(f"Error creating version record: {e}", exc_info=True)
                    next_version = None
        except Exception as backup_error:
            logger.error(f"Error creating template backup: {backup_error}", exc_info=True)
            next_version = None
        
        # Save charts (same logic as dashboard_template_charts_save)
        saved_charts = []
        if charts:
            logger.info(f"Saving {len(charts)} chart configurations")
            for chart_data in charts:
                chart_id = chart_data.get('chart_id')
                if not chart_id:
                    continue
                
                # Find or create config
                try:
                    config = ChartConfig.query.filter_by(
                        template_name=template_name,
                        chart_id=chart_id
                    ).first()
                except Exception as db_error:
                    logger.warning(f"Error querying ChartConfig: {db_error}")
                    config = None
                
                if not config:
                    config = ChartConfig(
                        template_name=template_name,
                        chart_id=chart_id,
                        created_by=current_user.id
                    )
                    db.session.add(config)
                
                # Update all fields
                new_title = chart_data.get('title')
                if new_title is not None and new_title != '':
                    config.title = new_title
                elif not config.title:
                    config.title = chart_id
                
                new_display_order = chart_data.get('display_order')
                if new_display_order is not None:
                    config.display_order = int(new_display_order)
                elif config.display_order is None:
                    config.display_order = 0
                
                new_chart_type = chart_data.get('chart_type')
                if new_chart_type:
                    config.chart_type = new_chart_type
                elif not config.chart_type:
                    config.chart_type = 'line'
                
                new_show_labels = chart_data.get('show_labels')
                if new_show_labels is not None:
                    config.show_labels = bool(new_show_labels)
                elif config.show_labels is None:
                    config.show_labels = True
                
                new_show_legend = chart_data.get('show_legend')
                if new_show_legend is not None:
                    config.show_legend = bool(new_show_legend)
                elif config.show_legend is None:
                    config.show_legend = True
                
                new_is_visible = chart_data.get('is_visible')
                if new_is_visible is not None:
                    config.is_visible = bool(new_is_visible)
                elif config.is_visible is None:
                    config.is_visible = True
                
                new_allow_export = chart_data.get('allow_export')
                if new_allow_export is not None:
                    config.allow_export = bool(new_allow_export)
                elif config.allow_export is None:
                    config.allow_export = True
                
                new_color_palette = chart_data.get('color_palette')
                if new_color_palette is not None:
                    # Validate palette name
                    if new_color_palette in COLOR_PALETTES:
                        config.color_palette = new_color_palette
                    else:
                        config.color_palette = 'default'
                        logger.warning(f"Invalid color_palette '{new_color_palette}' for {chart_id}, using default")
                elif config.color_palette is None:
                    config.color_palette = 'default'
                
                new_chart_options = chart_data.get('chart_options')
                if new_chart_options is not None:
                    config.chart_options = new_chart_options
                elif config.chart_options is None:
                    config.chart_options = {}
                
                config.updated_at = datetime.utcnow()
                
                # Log all saved fields for verification
                logger.info(f"Saving chart config for {chart_id}:")
                logger.info(f"  - title: '{config.title}'")
                logger.info(f"  - display_order: {config.display_order}")
                logger.info(f"  - chart_type: {config.chart_type}")
                logger.info(f"  - show_labels: {config.show_labels}")
                logger.info(f"  - show_legend: {config.show_legend}")
                logger.info(f"  - allow_export: {config.allow_export}")
                logger.info(f"  - chart_options: {bool(config.chart_options)}")
                
                saved_charts.append(config.to_dict())
        
        # Save tables (for now, just log - tables don't have database model yet)
        if tables:
            logger.info(f"Received {len(tables)} table configurations (table saving not yet implemented)")
            for table_data in tables:
                logger.debug(f"Table: {table_data.get('table_id')}, title: {table_data.get('title')}, order: {table_data.get('display_order')}")
        
        # Commit all changes to database
        try:
            db.session.commit()
            logger.info(f"✓ Successfully committed {len(saved_charts)} chart configurations to database")
            
            # Verify saved data by querying back
            for saved_chart in saved_charts:
                chart_id = saved_chart.get('chart_id')
                verify_config = ChartConfig.query.filter_by(
                    template_name=template_name,
                    chart_id=chart_id
                ).first()
                if verify_config:
                    logger.info(f"✓ Verified chart {chart_id} in database: type={verify_config.chart_type}, order={verify_config.display_order}")
                else:
                    logger.error(f"✗ Chart {chart_id} not found in database after commit!")
        except Exception as commit_error:
            db.session.rollback()
            logger.error(f"✗ Error committing settings to database: {commit_error}", exc_info=True)
            raise
        
        # Apply chart configurations to HTML file
        html_updated = False
        updated_html_content = None
        if saved_charts:
            try:
                logger.info(f"Applying {len(saved_charts)} chart configurations to HTML file: {template_path}")
                html_updated = apply_chart_configs_to_html(template_path, saved_charts)
                if html_updated:
                    logger.info(f"✓ HTML template {template_name} updated successfully")
                    # Read back to verify
                    with open(template_path, 'r', encoding='utf-8') as f:
                        updated_html_content = f.read()
                    
                    # Verify changes were applied by checking a few charts
                    import re
                    verification_count = 0
                    for saved_chart in saved_charts[:3]:  # Check first 3 charts
                        chart_id = saved_chart.get('chart_id')
                        chart_type = saved_chart.get('chart_type')
                        if chart_id and chart_type:
                            # Check if chart type exists in HTML
                            # Use exact match to ensure chart_id is not part of another id
                            escaped_chart_id = re.escape(chart_id)
                            ctx_pattern = rf'getElementById\s*\([\'"]{escaped_chart_id}(?![a-zA-Z0-9_])[\'"]\)'
                            if re.search(ctx_pattern, updated_html_content):
                                # Check if type is correct
                                type_pattern = rf"type\s*:\s*['\"]({re.escape(chart_type)})['\"]"
                                if re.search(type_pattern, updated_html_content):
                                    verification_count += 1
                                    logger.info(f"✓ Verified chart {chart_id} type '{chart_type}' in HTML")
                                else:
                                    logger.warning(f"⚠ Chart {chart_id} type '{chart_type}' not found in HTML after update")
                    if verification_count > 0:
                        logger.info(f"✓ Verified {verification_count} chart(s) in HTML file")
                    
                    # CRITICAL: Clear all caches to force immediate reload
                    try:
                        # 1. Touch the template file to update its modification time
                        # This ensures Flask/Jinja2 detects the file change
                        import os
                        os.utime(template_path, None)
                        logger.info(f"✓ Updated template file modification time: {template_path}")
                        
                        # 2. Clear Jinja2 template cache
                        from flask import current_app
                        try:
                            # Get the app instance (might be from request context or app context)
                            app_instance = current_app._get_current_object() if hasattr(current_app, '_get_current_object') else current_app
                            if hasattr(app_instance, 'jinja_env'):
                                if hasattr(app_instance.jinja_env, 'cache'):
                                    app_instance.jinja_env.cache.clear()
                                    logger.info("✓ Cleared Jinja2 template cache")
                                # Also try to reload the template loader
                                if hasattr(app_instance.jinja_env, 'loader'):
                                    # Force reload by clearing loader cache if it exists
                                    if hasattr(app_instance.jinja_env.loader, 'cache'):
                                        app_instance.jinja_env.loader.cache.clear()
                                        logger.info("✓ Cleared Jinja2 template loader cache")
                        except Exception as jinja_error:
                            logger.warning(f"Could not clear Jinja2 cache: {jinja_error}")
                        
                        # 3. Clear dashboard data cache for this specific dashboard
                        template_name_clean = template_name.replace('.html', '')
                        dashboard_id = template_name_clean  # e.g., 'd1', 'd2', etc.
                        try:
                            from dashboards.cache import DashboardCache
                            # Clear all cache entries for this dashboard
                            DashboardCache.clear(pattern=dashboard_id)
                            logger.info(f"✓ Cleared dashboard data cache for {dashboard_id}")
                        except Exception as cache_error:
                            logger.warning(f"Could not clear dashboard cache: {cache_error}")
                        
                        # 4. Also clear all dashboard caches to be safe (template changes affect all users)
                        try:
                            from dashboards.cache import DashboardCache
                            DashboardCache.clear()  # Clear all dashboard caches
                            logger.info("✓ Cleared all dashboard caches (template changes affect all users)")
                        except Exception as full_cache_error:
                            logger.warning(f"Could not clear all dashboard caches: {full_cache_error}")
                    except Exception as cache_clear_error:
                        logger.error(f"✗ Error clearing caches: {cache_clear_error}", exc_info=True)
                else:
                    logger.warning(f"⚠ Could not update HTML template {template_name} (no changes detected)")
            except Exception as html_error:
                logger.error(f"✗ Error updating HTML template: {html_error}", exc_info=True)
                # Don't fail the whole operation if HTML update fails - database save was successful
        
        # Update TemplateVersion with final HTML content
        if html_updated and updated_html_content and next_version:
            try:
                version = TemplateVersion.query.filter_by(
                    template_name=template_name,
                    version_number=next_version
                ).first()
                if version:
                    version.template_content = updated_html_content
                    version.chart_configs = saved_charts
                    db.session.commit()
                    logger.info(f"Updated template version {next_version} with final HTML content")
            except Exception as version_update_error:
                logger.warning(f"Error updating template version: {version_update_error}")
        
        # Prepare detailed success message
        charts_summary = []
        for saved_chart in saved_charts:
            charts_summary.append(f"{saved_chart.get('chart_id')} (type: {saved_chart.get('chart_type')}, order: {saved_chart.get('display_order')})")
        
        logger.info("=" * 60)
        logger.info(f"SAVE OPERATION SUMMARY for {template_name}:")
        logger.info(f"  - Charts saved to database: {len(saved_charts)}")
        for chart in saved_charts:
            logger.info(f"    • {chart.get('chart_id')}: type={chart.get('chart_type')}, order={chart.get('display_order')}, title='{chart.get('title')}'")
        logger.info(f"  - HTML file updated: {html_updated}")
        logger.info(f"  - Backup version created: {next_version}")
        logger.info("=" * 60)
        
        if next_version:
            if html_updated:
                message = f'✓ {len(saved_charts)} تنظیمات نمودار و {len(tables)} تنظیمات جدول با موفقیت ذخیره شد.\n✓ فایل HTML به‌روزرسانی شد.\n✓ نسخه پشتیبان {next_version} ایجاد شد.'
            else:
                message = f'✓ {len(saved_charts)} تنظیمات نمودار و {len(tables)} تنظیمات جدول در دیتابیس ذخیره شد.\n⚠ فایل HTML به‌روزرسانی نشد (تغییری یافت نشد یا خطا رخ داد).\n✓ نسخه پشتیبان {next_version} ایجاد شد.'
        else:
            if html_updated:
                message = f'✓ {len(saved_charts)} تنظیمات نمودار و {len(tables)} تنظیمات جدول ذخیره شد.\n✓ فایل HTML به‌روزرسانی شد.'
            else:
                message = f'✓ {len(saved_charts)} تنظیمات نمودار و {len(tables)} تنظیمات جدول در دیتابیس ذخیره شد.\n⚠ فایل HTML به‌روزرسانی نشد (تغییری یافت نشد یا خطا رخ داد).'
        
        return jsonify({
            'success': True,
            'message': message,
            'charts_saved': len(saved_charts),
            'tables_saved': len(tables),
            'version': next_version,
            'html_updated': html_updated,
            'details': {
                'charts': [{'id': c.get('chart_id'), 'type': c.get('chart_type'), 'order': c.get('display_order')} for c in saved_charts]
            }
        })
        
    except Exception as e:
        logger.error(f"Error saving template settings: {e}", exc_info=True)
        return jsonify({'success': False, 'message': f'خطا: {str(e)}'}), 500


@admin_bp.route('/dashboards/templates/<template_name>/charts', methods=['POST'])
@login_required
@admin_required
def dashboard_template_charts_save(template_name):
    """Save chart configurations for a template"""
    try:
        log_action('save_chart_configs', 'template', template_name)
    except Exception as e:
        logger.warning(f"Error logging action: {e}")
    
    try:
        # Security check
        if not template_name.endswith('.html') or '..' in template_name or '/' in template_name:
            return jsonify({'success': False, 'message': 'نام فایل نامعتبر است'}), 400
        
        # Get template path
        base_dir = Path(__file__).parent.parent
        template_path = base_dir / 'templates' / 'dashboards' / template_name
        
        if not template_path.exists():
            return jsonify({'success': False, 'message': 'تمپلیت یافت نشد'}), 404
        
        # Create backup before making changes
        next_version = None
        try:
            # Read current template content
            with open(template_path, 'r', encoding='utf-8') as f:
                current_content = f.read()
            
            # Get current chart configs
            current_chart_configs = []
            try:
                configs = ChartConfig.query.filter_by(template_name=template_name).all()
                current_chart_configs = [config.to_dict() for config in configs]
            except Exception as e:
                logger.warning(f"Error getting current chart configs: {e}")
            
            # Get next version number
            try:
                max_version = db.session.query(func.max(TemplateVersion.version_number)).filter_by(
                    template_name=template_name
                ).scalar() or 0
                next_version = max_version + 1
            except Exception as e:
                logger.warning(f"Error getting max version number: {e}")
                next_version = 1
            
            # Keep only last 50 versions
            if next_version and next_version > 50:
                try:
                    # Delete oldest versions
                    versions_to_delete = TemplateVersion.query.filter_by(
                        template_name=template_name
                    ).order_by(TemplateVersion.version_number.asc()).limit(next_version - 50).all()
                    for version in versions_to_delete:
                        db.session.delete(version)
                except Exception as e:
                    logger.warning(f"Error deleting old versions: {e}")
            
            # Create version backup
            if next_version:
                try:
                    version = TemplateVersion(
                        template_name=template_name,
                        version_number=next_version,
                        template_content=current_content,
                        chart_configs=current_chart_configs,
                        created_by=current_user.id,
                        description=f'ذخیره خودکار قبل از اعمال تغییرات - نسخه {next_version}'
                    )
                    db.session.add(version)
                    db.session.flush()  # Flush to get version ID
                    
                    logger.info(f"Created template version {next_version} for {template_name}")
                except Exception as e:
                    logger.error(f"Error creating version record: {e}", exc_info=True)
                    next_version = None  # Reset if creation failed
        except Exception as backup_error:
            logger.error(f"Error creating template backup: {backup_error}", exc_info=True)
            # Continue even if backup fails, but log the error
            # Don't fail the save operation if backup fails
            next_version = None
        
        # Get data from request
        if not request.is_json:
            return jsonify({'success': False, 'message': 'درخواست باید JSON باشد'}), 400
        
        data = request.get_json()
        charts = data.get('charts', [])
        
        # Log received data for debugging
        logger.info(f"Received chart data for {template_name}: {len(charts)} charts")
        for idx, chart_data in enumerate(charts):
            logger.info(f"Chart {idx}: id={chart_data.get('chart_id')}, title={chart_data.get('title')}, order={chart_data.get('display_order')}, type={chart_data.get('chart_type')}")
        
        if not charts:
            return jsonify({'success': False, 'message': 'هیچ نموداری ارسال نشده است'}), 400
        
        saved_charts = []
        for chart_data in charts:
            chart_id = chart_data.get('chart_id')
            if not chart_id:
                continue
            
            # Find or create config
            try:
                config = ChartConfig.query.filter_by(
                    template_name=template_name,
                    chart_id=chart_id
                ).first()
            except Exception as db_error:
                logger.warning(f"Error querying ChartConfig: {db_error}")
                config = None
            
            if not config:
                config = ChartConfig(
                    template_name=template_name,
                    chart_id=chart_id,
                    created_by=current_user.id
                )
                db.session.add(config)
            
            # Update config - ensure all fields are saved
            # Get values from request data, fallback to existing config, then to defaults
            new_title = chart_data.get('title')
            if new_title is not None and new_title != '':
                config.title = new_title
            elif not config.title:
                config.title = chart_id
            
            new_display_order = chart_data.get('display_order')
            if new_display_order is not None:
                config.display_order = int(new_display_order)
            elif config.display_order is None:
                config.display_order = 0
            
            new_chart_type = chart_data.get('chart_type')
            if new_chart_type:
                config.chart_type = new_chart_type
            elif not config.chart_type:
                config.chart_type = 'line'
            
            new_show_labels = chart_data.get('show_labels')
            if new_show_labels is not None:
                config.show_labels = bool(new_show_labels)
            elif config.show_labels is None:
                config.show_labels = True
            
            new_show_legend = chart_data.get('show_legend')
            if new_show_legend is not None:
                config.show_legend = bool(new_show_legend)
            elif config.show_legend is None:
                config.show_legend = True
            
            new_is_visible = chart_data.get('is_visible')
            if new_is_visible is not None:
                config.is_visible = bool(new_is_visible)
            elif config.is_visible is None:
                config.is_visible = True
            
            new_allow_export = chart_data.get('allow_export')
            if new_allow_export is not None:
                config.allow_export = bool(new_allow_export)
            elif config.allow_export is None:
                config.allow_export = True
            
            new_chart_options = chart_data.get('chart_options')
            if new_chart_options is not None:
                config.chart_options = new_chart_options
            elif config.chart_options is None:
                config.chart_options = {}
            
            config.updated_at = datetime.utcnow()
            
            # Log for debugging
            logger.info(f"Saving chart config: {chart_id}, title: '{config.title}', order: {config.display_order}, type: {config.chart_type}, labels: {config.show_labels}, legend: {config.show_legend}, export: {config.allow_export}")
            
            saved_charts.append(config.to_dict())
        
        try:
            db.session.commit()
        except Exception as commit_error:
            db.session.rollback()
            logger.error(f"Error committing chart configs: {commit_error}", exc_info=True)
            raise
        
        # Log saved data for verification
        logger.info(f"Chart configs for {template_name} updated by user {current_user.id}")
        for saved_chart in saved_charts:
            logger.info(f"Saved chart: id={saved_chart.get('chart_id')}, title='{saved_chart.get('title')}', order={saved_chart.get('display_order')}, type={saved_chart.get('chart_type')}, labels={saved_chart.get('show_labels')}, legend={saved_chart.get('show_legend')}, export={saved_chart.get('allow_export')}")
        
        # Apply chart configurations to HTML file
        html_updated = False
        updated_html_content = None
        try:
            html_updated = apply_chart_configs_to_html(template_path, saved_charts)
            if html_updated:
                logger.info(f"HTML template {template_name} updated with chart configurations")
                # Read the updated HTML content to ensure it matches what's saved
                with open(template_path, 'r', encoding='utf-8') as f:
                    updated_html_content = f.read()
            else:
                logger.warning(f"Could not update HTML template {template_name} with chart configurations")
        except Exception as html_error:
            logger.error(f"Error updating HTML template: {html_error}", exc_info=True)
            # Continue even if HTML update fails - database save was successful
        
        # Update TemplateVersion with the final HTML content if it was updated
        # This ensures the version in database matches the actual HTML file
        if html_updated and updated_html_content and next_version:
            try:
                # Find the version we just created
                version = TemplateVersion.query.filter_by(
                    template_name=template_name,
                    version_number=next_version
                ).first()
                
                if version:
                    # Update with the final HTML content (after apply_chart_configs_to_html)
                    version.template_content = updated_html_content
                    # Also update chart_configs with the saved charts
                    version.chart_configs = saved_charts
                    db.session.commit()
                    logger.info(f"Updated template version {next_version} with final HTML content for {template_name}")
            except Exception as version_update_error:
                logger.warning(f"Error updating template version with final HTML: {version_update_error}")
                # Don't fail the operation if version update fails
        
        # Prepare success message
        if next_version:
            if html_updated:
                message = f'{len(saved_charts)} تنظیمات نمودار ذخیره شد و فایل HTML به‌روزرسانی شد. نسخه پشتیبان {next_version} ایجاد شد.'
            else:
                message = f'{len(saved_charts)} تنظیمات نمودار در دیتابیس ذخیره شد. (خطا در به‌روزرسانی فایل HTML) نسخه پشتیبان {next_version} ایجاد شد.'
        else:
            if html_updated:
                message = f'{len(saved_charts)} تنظیمات نمودار ذخیره شد و فایل HTML به‌روزرسانی شد.'
            else:
                message = f'{len(saved_charts)} تنظیمات نمودار در دیتابیس ذخیره شد. (خطا در به‌روزرسانی فایل HTML یا ایجاد نسخه پشتیبان)'
        
        return jsonify({
            'success': True,
            'message': message,
            'charts': saved_charts,
            'version_number': next_version,
            'html_updated': html_updated
        })
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error saving chart configs for {template_name}: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'message': f'خطا در ذخیره تنظیمات: {str(e)}'
        }), 500


@admin_bp.route('/dashboards/templates/<template_name>/versions', methods=['GET'])
@login_required
@admin_required
def dashboard_template_versions(template_name):
    """Get version history for a template"""
    try:
        # Security check
        if not template_name.endswith('.html') or '..' in template_name or '/' in template_name:
            return jsonify({'success': False, 'message': 'نام فایل نامعتبر است'}), 400
        
        # Get versions (newest first)
        versions = TemplateVersion.query.filter_by(
            template_name=template_name
        ).order_by(TemplateVersion.version_number.desc()).limit(50).all()
        
        return jsonify({
            'success': True,
            'versions': [v.to_dict() for v in versions]
        })
    except Exception as e:
        logger.error(f"Error getting template versions for {template_name}: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'message': f'خطا در دریافت نسخه‌ها: {str(e)}'
        }), 500


@admin_bp.route('/dashboards/templates/<template_name>/versions/<int:version_number>/restore', methods=['POST'])
@login_required
@admin_required
def dashboard_template_restore_version(template_name, version_number):
    """Restore a template to a previous version"""
    try:
        # Security check
        if not template_name.endswith('.html') or '..' in template_name or '/' in template_name:
            return jsonify({'success': False, 'message': 'نام فایل نامعتبر است'}), 400
        
        # Get version
        version = TemplateVersion.query.filter_by(
            template_name=template_name,
            version_number=version_number
        ).first()
        
        if not version:
            return jsonify({'success': False, 'message': 'نسخه یافت نشد'}), 404
        
        # Get template path
        base_dir = Path(__file__).parent.parent
        template_path = base_dir / 'templates' / 'dashboards' / template_name
        
        if not template_path.exists():
            return jsonify({'success': False, 'message': 'تمپلیت یافت نشد'}), 404
        
        # Restore template content (no backup created before restore)
        try:
            with open(template_path, 'w', encoding='utf-8') as f:
                f.write(version.template_content)
        except Exception as e:
            logger.error(f"Error restoring template content: {e}", exc_info=True)
            return jsonify({'success': False, 'message': f'خطا در بازگردانی محتوای تمپلیت: {str(e)}'}), 500
        
        # Restore chart configs if available
        if version.chart_configs:
            try:
                # Delete existing configs
                ChartConfig.query.filter_by(template_name=template_name).delete()
                
                # Restore configs - ensure all fields are restored
                for config_data in version.chart_configs:
                    config = ChartConfig(
                        template_name=config_data.get('template_name', template_name),
                        chart_id=config_data.get('chart_id'),
                        title=config_data.get('title') or config_data.get('chart_id', ''),
                        display_order=int(config_data.get('display_order', 0)),
                        chart_type=config_data.get('chart_type', 'line'),
                        show_labels=bool(config_data.get('show_labels', True)),
                        show_legend=bool(config_data.get('show_legend', True)),
                        allow_export=bool(config_data.get('allow_export', True)),
                        chart_options=config_data.get('chart_options', {}),
                        created_by=current_user.id
                    )
                    db.session.add(config)
                    logger.debug(f"Restoring chart config: {config.chart_id}, title: {config.title}, order: {config.display_order}, type: {config.chart_type}")
            except Exception as e:
                logger.warning(f"Error restoring chart configs: {e}", exc_info=True)
                # Continue even if chart config restore fails
        
        db.session.commit()
        
        log_action('restore_template_version', 'template', template_name, {'version': version_number})
        
        logger.info(f"Template {template_name} restored to version {version_number} by user {current_user.id}")
        
        return jsonify({
            'success': True,
            'message': f'تمپلیت به نسخه {version_number} بازگردانده شد'
        })
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error restoring template version: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'message': f'خطا در بازگردانی نسخه: {str(e)}'
        }), 500


@admin_bp.route('/dashboards/templates/<template_name>/versions/<int:version_number>/delete', methods=['POST'])
@login_required
@admin_required
def dashboard_template_delete_version(template_name, version_number):
    """Delete a template version"""
    try:
        # Security check
        if not template_name.endswith('.html') or '..' in template_name or '/' in template_name:
            return jsonify({'success': False, 'message': 'نام فایل نامعتبر است'}), 400
        
        # Get version
        version = TemplateVersion.query.filter_by(
            template_name=template_name,
            version_number=version_number
        ).first()
        
        if not version:
            return jsonify({'success': False, 'message': 'نسخه یافت نشد'}), 404
        
        # Delete version
        db.session.delete(version)
        db.session.commit()
        
        log_action('delete_template_version', 'template', template_name, {'version': version_number})
        
        logger.info(f"Template version {version_number} for {template_name} deleted by user {current_user.id}")
        
        return jsonify({
            'success': True,
            'message': f'نسخه {version_number} با موفقیت حذف شد'
        })
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error deleting template version: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'message': f'خطا در حذف نسخه: {str(e)}'
        }), 500


@admin_bp.route('/dashboards/templates/<template_name>/charts/<chart_id>/preview', methods=['POST'])
@login_required
@admin_required
def dashboard_template_chart_preview(template_name, chart_id):
    """Preview changes for a single chart before saving"""
    try:
        # Security check
        if not template_name.endswith('.html') or '..' in template_name or '/' in template_name:
            return jsonify({'success': False, 'message': 'نام فایل نامعتبر است'}), 400
        
        # Get template path
        base_dir = Path(__file__).parent.parent
        template_path = base_dir / 'templates' / 'dashboards' / template_name
        
        if not template_path.exists():
            return jsonify({'success': False, 'message': 'تمپلیت یافت نشد'}), 404
        
        # Read current template content
        with open(template_path, 'r', encoding='utf-8') as f:
            current_content = f.read()
        
        # Get data from request
        if not request.is_json:
            return jsonify({'success': False, 'message': 'درخواست باید JSON باشد'}), 400
        
        data = request.get_json()
        chart_data = data.get('chart', {})
        
        if not chart_data or chart_data.get('chart_id') != chart_id:
            return jsonify({'success': False, 'message': 'اطلاعات نمودار نامعتبر است'}), 400
        
        # Log the chart_id being processed
        logger.info(f"Preview: Extracting code for chart_id='{chart_id}' (from URL parameter)")
        logger.info(f"Preview: chart_data.chart_id='{chart_data.get('chart_id')}' (from request body)")
        
        # Ensure chart_id matches
        if chart_data.get('chart_id') != chart_id:
            logger.error(f"Chart ID mismatch: URL has '{chart_id}' but request has '{chart_data.get('chart_id')}'")
            return jsonify({'success': False, 'message': 'عدم تطابق ID نمودار'}), 400
        
        # Extract current chart code from template
        logger.info(f"Preview: Extracting before_code for chart_id='{chart_id}'")
        before_code = extract_chart_code(current_content, chart_id)
        
        # Verify that before_code contains the correct chart_id
        if chart_id not in before_code and 'not found' not in before_code:
            logger.warning(f"Preview: before_code might be for wrong chart. Looking for '{chart_id}' in code...")
            # Check if wrong chart_id is in the code
            if 'genderChart404' in before_code and chart_id == 'genderChart':
                logger.error(f"Preview: ERROR! Extracted code for 'genderChart404' when looking for 'genderChart'")
            elif 'genderChart' in before_code and chart_id == 'genderChart404':
                logger.error(f"Preview: ERROR! Extracted code for 'genderChart' when looking for 'genderChart404'")
        
        # Apply changes to get after code
        # Use apply_chart_configs_to_html logic but collect changes instead of applying
        test_content = current_content
        changes = []
        
        # Collect changes using the same logic as apply_chart_configs_to_html
        # but only for this specific chart
        chart_configs = [chart_data]
        
        # Apply the same logic as apply_chart_configs_to_html
        # We'll create a temporary file and use the existing function
        import tempfile
        import shutil
        
        # Create a temporary copy of the template
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', delete=False, suffix='.html') as tmp_file:
            tmp_file.write(test_content)
            tmp_path = Path(tmp_file.name)
        
        try:
            # Apply chart configs (this will modify the file)
            logger.info(f"Preview: Applying configs for chart_id='{chart_id}'")
            apply_chart_configs_to_html(tmp_path, chart_configs)
            
            # Read the modified content
            with open(tmp_path, 'r', encoding='utf-8') as f:
                after_content = f.read()
            
            # Extract after code
            logger.info(f"Preview: Extracting after_code for chart_id='{chart_id}'")
            after_code = extract_chart_code(after_content, chart_id)
            
            # Verify after_code
            if chart_id not in after_code and 'not found' not in after_code:
                logger.warning(f"Preview: after_code might be for wrong chart. Looking for '{chart_id}' in code...")
        finally:
            # Clean up temporary file
            try:
                tmp_path.unlink()
            except:
                pass
        
        return jsonify({
            'success': True,
            'before_code': before_code,
            'after_code': after_code,
            'chart_id': chart_id
        })
        
    except Exception as e:
        logger.error(f"Error previewing chart {chart_id} for {template_name}: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'message': f'خطا در پیش‌نمایش: {str(e)}'
        }), 500


@admin_bp.route('/dashboards/templates/<template_name>/charts/<chart_id>/save', methods=['POST'])
@login_required
@admin_required
def dashboard_template_chart_save(template_name, chart_id):
    """Save a single chart configuration"""
    try:
        log_action('save_single_chart_config', 'template', template_name, {'chart_id': chart_id})
    except Exception as e:
        logger.warning(f"Error logging action: {e}")
    
    try:
        # Security check
        if not template_name.endswith('.html') or '..' in template_name or '/' in template_name:
            return jsonify({'success': False, 'message': 'نام فایل نامعتبر است'}), 400
        
        # Get template path
        base_dir = Path(__file__).parent.parent
        template_path = base_dir / 'templates' / 'dashboards' / template_name
        
        if not template_path.exists():
            return jsonify({'success': False, 'message': 'تمپلیت یافت نشد'}), 404
        
        # Create backup before making changes
        next_version = None
        try:
            # Read current template content
            with open(template_path, 'r', encoding='utf-8') as f:
                current_content = f.read()
            
            # Get current chart configs
            current_chart_configs = []
            try:
                configs = ChartConfig.query.filter_by(template_name=template_name).all()
                current_chart_configs = [config.to_dict() for config in configs]
            except Exception as e:
                logger.warning(f"Error getting current chart configs: {e}")
            
            # Get next version number
            try:
                max_version = db.session.query(func.max(TemplateVersion.version_number)).filter_by(
                    template_name=template_name
                ).scalar() or 0
                next_version = max_version + 1
            except Exception as e:
                logger.warning(f"Error getting max version number: {e}")
                next_version = 1
            
            # Keep only last 50 versions
            if next_version and next_version > 50:
                try:
                    versions_to_delete = TemplateVersion.query.filter_by(
                        template_name=template_name
                    ).order_by(TemplateVersion.version_number.asc()).limit(next_version - 50).all()
                    for version in versions_to_delete:
                        db.session.delete(version)
                except Exception as e:
                    logger.warning(f"Error deleting old versions: {e}")
            
            # Create version backup
            if next_version:
                try:
                    version = TemplateVersion(
                        template_name=template_name,
                        version_number=next_version,
                        template_content=current_content,
                        chart_configs=current_chart_configs,
                        created_by=current_user.id,
                        description=f'ذخیره خودکار قبل از اعمال تغییرات نمودار {chart_id} - نسخه {next_version}'
                    )
                    db.session.add(version)
                    db.session.flush()
                    logger.info(f"Created template version {next_version} for {template_name}")
                except Exception as e:
                    logger.error(f"Error creating version record: {e}", exc_info=True)
                    next_version = None
        except Exception as backup_error:
            logger.error(f"Error creating template backup: {backup_error}", exc_info=True)
            next_version = None
        
        # Get data from request
        if not request.is_json:
            return jsonify({'success': False, 'message': 'درخواست باید JSON باشد'}), 400
        
        data = request.get_json()
        chart_data = data.get('chart', {})
        
        if not chart_data or chart_data.get('chart_id') != chart_id:
            return jsonify({'success': False, 'message': 'اطلاعات نمودار نامعتبر است'}), 400
        
        # Save chart config to database
        try:
            config = ChartConfig.query.filter_by(
                template_name=template_name,
                chart_id=chart_id
            ).first()
            
            if not config:
                config = ChartConfig(
                    template_name=template_name,
                    chart_id=chart_id,
                    created_by=current_user.id
                )
                db.session.add(config)
            
            # Update config
            new_title = chart_data.get('title')
            if new_title is not None and new_title != '':
                config.title = new_title
            elif not config.title:
                config.title = chart_id
            
            new_display_order = chart_data.get('display_order')
            if new_display_order is not None:
                config.display_order = int(new_display_order)
            elif config.display_order is None:
                config.display_order = 0
            
            new_chart_type = chart_data.get('chart_type')
            if new_chart_type:
                config.chart_type = new_chart_type
            elif not config.chart_type:
                config.chart_type = 'line'
            
            new_show_labels = chart_data.get('show_labels')
            if new_show_labels is not None:
                config.show_labels = bool(new_show_labels)
            elif config.show_labels is None:
                config.show_labels = True
            
            new_show_legend = chart_data.get('show_legend')
            if new_show_legend is not None:
                config.show_legend = bool(new_show_legend)
            elif config.show_legend is None:
                config.show_legend = True
            
            new_is_visible = chart_data.get('is_visible')
            if new_is_visible is not None:
                config.is_visible = bool(new_is_visible)
            elif config.is_visible is None:
                config.is_visible = True
            
            new_allow_export = chart_data.get('allow_export')
            if new_allow_export is not None:
                config.allow_export = bool(new_allow_export)
            elif config.allow_export is None:
                config.allow_export = True
            
            new_color_palette = chart_data.get('color_palette')
            if new_color_palette:
                config.color_palette = new_color_palette
            elif not config.color_palette:
                config.color_palette = 'default'
            
            new_chart_options = chart_data.get('chart_options')
            if new_chart_options is not None:
                config.chart_options = new_chart_options
            elif config.chart_options is None:
                config.chart_options = {}
            
            config.updated_at = datetime.utcnow()
            
            db.session.commit()
            logger.info(f"Saved chart config: {chart_id}, title: '{config.title}', type: {config.chart_type}")
        except Exception as db_error:
            db.session.rollback()
            logger.error(f"Error saving chart config: {db_error}", exc_info=True)
            return jsonify({'success': False, 'message': f'خطا در ذخیره تنظیمات: {str(db_error)}'}), 500
        
        # Apply chart configuration to HTML file
        try:
            html_updated = apply_chart_configs_to_html(template_path, [chart_data])
            if html_updated:
                logger.info(f"HTML template {template_name} updated with chart {chart_id} configuration")
            else:
                logger.warning(f"HTML template {template_name} was not updated for chart {chart_id}")
        except Exception as html_error:
            logger.error(f"Error applying chart config to HTML: {html_error}", exc_info=True)
            # Don't fail the request if HTML update fails, but log it
        
        return jsonify({
            'success': True,
            'message': f'نمودار "{chart_data.get("title", chart_id)}" با موفقیت ذخیره شد',
            'chart_id': chart_id
        })
        
    except Exception as e:
        logger.error(f"Error saving chart {chart_id} for {template_name}: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'message': f'خطا در ذخیره: {str(e)}'
        }), 500


def extract_charts_from_template(content: str) -> list:
    """
    Extract all charts from template HTML content.
    Returns a list of dictionaries with 'title' and 'chart_id' keys.
    """
    import re
    charts = []
    
    # First, find all canvas elements with ids
    canvas_pattern = r'<canvas[^>]*id\s*=\s*["\']([^"\']+)["\'][^>]*>'
    canvas_matches = list(re.finditer(canvas_pattern, content, re.IGNORECASE))
    
    for canvas_match in canvas_matches:
        chart_id = canvas_match.group(1).strip()
        if not chart_id:
            continue
        
        # Find title before this canvas (look back up to 1000 chars)
        canvas_pos = canvas_match.start()
        search_start = max(0, canvas_pos - 1000)
        search_content = content[search_start:canvas_pos]
        
        # Look for h4/h5/h3 with card-title class (most common pattern)
        title_patterns = [
            r'<h[345][^>]*class=["\'][^"\']*card-title[^"\']*["\'][^>]*>([^<]+)</h[345]>',
            r'<h[345][^>]*>([^<]+)</h[345]>',  # Fallback: any h3/h4/h5
        ]
        
        title = None
        for pattern in title_patterns:
            title_matches = list(re.finditer(pattern, search_content, re.IGNORECASE))
            if title_matches:
                # Get the last match (closest to canvas)
                title_match = title_matches[-1]
                title = title_match.group(1).strip()
                break
        
        # If no title found, use chart_id as title
        if not title:
            title = chart_id
        
        charts.append({
            'title': title,
            'chart_id': chart_id
        })
    
    # Sort by position in document (maintain order)
    charts_with_pos = []
    for chart in charts:
        # Find position of this chart_id in content
        escaped_id = re.escape(chart['chart_id'])
        id_pattern = rf'id\s*=\s*["\']{escaped_id}(?![a-zA-Z0-9_])["\']'
        id_match = re.search(id_pattern, content, re.IGNORECASE)
        pos = id_match.start() if id_match else 999999
        charts_with_pos.append((pos, chart))
    
    # Sort by position and return
    charts_with_pos.sort(key=lambda x: x[0])
    return [chart for _, chart in charts_with_pos]


def extract_chart_code(content: str, chart_id: str) -> str:
    """Extract the JavaScript code for a specific chart"""
    import re
    
    logger.info(f"extract_chart_code: Looking for chart_id='{chart_id}'")
    
    # Find getElementById for this chart_id
    # Use exact match to ensure chart_id is not part of another id
    escaped_chart_id = re.escape(chart_id)
    # Pattern: getElementById('chart_id') where chart_id is exact (not part of longer id)
    # CRITICAL: We need to ensure the quote immediately follows chart_id, not alphanumeric chars
    # Pattern breakdown:
    # - getElementById\s*\(  : matches "getElementById(" with optional spaces
    # - [\'"]                 : matches opening quote (' or ")
    # - {escaped_chart_id}    : matches the exact chart_id
    # - (?![a-zA-Z0-9_])     : negative lookahead - ensures no alphanumeric/underscore follows
    # - [\'"]                 : matches closing quote (must immediately follow chart_id)
    # - \)                    : matches closing parenthesis
    # This ensures 'genderChart' matches but 'genderChart404' does NOT
    ctx_pattern = rf'getElementById\s*\([\'"]{escaped_chart_id}(?![a-zA-Z0-9_])[\'"]\)'
    
    # Find all potential matches
    all_matches = list(re.finditer(ctx_pattern, content))
    
    logger.info(f"extract_chart_code: Found {len(all_matches)} potential matches for pattern")
    
    if not all_matches:
        logger.warning(f"extract_chart_code: No matches found for chart_id='{chart_id}'")
        return f"// Chart {chart_id} not found in template"
    
    # Verify each match to ensure the extracted ID is exactly chart_id
    # This is critical because 'genderChart' could incorrectly match 'genderChart404'
    ctx_match = None
    for i, match in enumerate(all_matches):
        # Get the full matched string
        full_match = match.group(0)
        logger.debug(f"extract_chart_code: Match {i+1}: {full_match[:100]}")
        
        # Extract the ID directly from the match using a simpler, more reliable method
        # Find the quoted string that contains the chart_id
        # Pattern: quote, then any characters, then quote - but we need the one with our chart_id
        # Better approach: find the quoted string and verify it's exactly chart_id
        quoted_id_pattern = rf'[\'"]([^\'"]+)[\'"]'
        quoted_matches = list(re.finditer(quoted_id_pattern, full_match))
        
        found_exact_match = False
        for quoted_match in quoted_matches:
            extracted_id = quoted_match.group(1)  # Get the content inside quotes
            logger.debug(f"extract_chart_code: Match {i+1} found quoted ID: '{extracted_id}'")
            
            # CRITICAL CHECK: extracted ID must be exactly chart_id
            # This prevents 'genderChart' from matching 'genderChart404'
            if extracted_id == chart_id:
                ctx_match = match
                found_exact_match = True
                logger.info(f"extract_chart_code: ✓ Found exact match for chart_id '{chart_id}' at position {match.start()}")
                break
            elif chart_id in extracted_id and extracted_id != chart_id:
                # This is a substring match (e.g., 'genderChart' in 'genderChart404')
                logger.warning(f"extract_chart_code: ✗ Match {i+1} rejected: extracted_id '{extracted_id}' contains '{chart_id}' but is not exact match")
        
        if found_exact_match:
            break
    
    if not ctx_match:
        # If no exact match found, log all matches for debugging
        logger.error(f"extract_chart_code: ✗ No exact match found for chart_id '{chart_id}'. Found {len(all_matches)} potential matches.")
        for i, match in enumerate(all_matches[:5]):  # Log first 5 matches
            logger.error(f"  Match {i+1}: {match.group(0)[:150]}")
        return f"// Chart {chart_id} not found in template (found {len(all_matches)} matches but none were exact)"
    
    # Find the Chart initialization after this context
    # CRITICAL: We need to find the Chart initialization that uses our exact chart_id
    # Better approach: Search for Chart initialization that contains our chart_id directly
    start_pos = ctx_match.end()
    
    # Look for Chart initialization that contains our chart_id
    # We'll search for the pattern: new Chart(...getElementById('chart_id')...)
    # This is more reliable than searching separately
    escaped_chart_id = re.escape(chart_id)
    
    # Search in a reasonable distance after getElementById
    search_distance = 500
    chart_block = content[start_pos:start_pos + search_distance]
    
    logger.debug(f"extract_chart_code: Searching for Chart initialization with chart_id '{chart_id}' in {len(chart_block)} chars")
    
    # Method 1: Find Chart initialization that contains our exact chart_id
    # Search for pattern: new Chart(...getElementById('chart_id')..., {
    # Use a simpler, more reliable approach
    
    # Pattern that matches Chart initialization with our exact chart_id
    # This pattern looks for: new Chart( ... getElementById('chart_id') ... , {
    chart_init_pattern = rf'new\s+Chart\s*\([^)]*getElementById\s*\(\s*[\'"]{escaped_chart_id}(?![a-zA-Z0-9_])[\'"]\s*\)[^)]*,\s*{{'
    
    logger.debug(f"extract_chart_code: Searching for pattern: new Chart(...getElementById('{chart_id}')..., {{")
    pattern_match = re.search(chart_init_pattern, chart_block, re.DOTALL)
    
    chart_init_match = None
    if pattern_match:
        # Verify the match by extracting the ID from it
        match_text = pattern_match.group(0)
        logger.debug(f"extract_chart_code: Pattern matched, verifying: {match_text[:150]}")
        
        # Extract all IDs from the match
        id_pattern = rf'getElementById\s*\(\s*[\'"]([^\'"]+)[\'"]\s*\)'
        id_matches = list(re.finditer(id_pattern, match_text))
        
        if id_matches:
            # Use the last match (should be the one in Chart initialization)
            last_id_match = id_matches[-1]
            extracted_id = last_id_match.group(1)
            
            logger.debug(f"extract_chart_code: Extracted ID from match: '{extracted_id}' (looking for '{chart_id}')")
            
            # CRITICAL: Must be exact match
            if extracted_id == chart_id:
                chart_init_match = pattern_match
                logger.info(f"extract_chart_code: ✓ Verified Chart initialization for '{chart_id}'")
            else:
                logger.warning(f"extract_chart_code: ✗ Pattern matched but extracted ID '{extracted_id}' != '{chart_id}', rejecting")
        else:
            logger.warning(f"extract_chart_code: Pattern matched but could not extract ID from: {match_text[:150]}")
    
    if chart_init_match:
        logger.info(f"extract_chart_code: ✓ Direct pattern match found for '{chart_id}' at offset {chart_init_match.start()}")
    else:
        # Try larger search distance
        logger.debug(f"extract_chart_code: No match in first {search_distance} chars, trying larger distance")
        search_distance = 2000
        chart_block = content[start_pos:start_pos + search_distance]
        chart_init_match = re.search(chart_init_pattern, chart_block, re.DOTALL)
        
        if chart_init_match:
            logger.info(f"extract_chart_code: ✓ Direct pattern match found for '{chart_id}' at offset {chart_init_match.start()} (in extended search)")
    
    if not chart_init_match:
        # Fallback: Find any Chart initialization and verify it uses our chart_id
        logger.warning(f"extract_chart_code: Direct pattern match failed, trying fallback method")
        all_chart_inits = list(re.finditer(r'new\s+Chart\s*\([^,]+,\s*\{', chart_block))
        
        if not all_chart_inits:
            logger.warning(f"extract_chart_code: No Chart initialization found within {search_distance} chars after getElementById for '{chart_id}'")
            return f"// Chart initialization for {chart_id} not found"
        
        logger.debug(f"extract_chart_code: Fallback - Found {len(all_chart_inits)} Chart initializations, checking each one")
        
        # Check each Chart initialization
        for chart_init in all_chart_inits:
            chart_init_start = start_pos + chart_init.start()
            chart_init_end = start_pos + chart_init.end()
            lookback_start = max(0, chart_init_start - 200)
            chart_init_context = content[lookback_start:chart_init_end + 100]
            
            # Find ALL getElementById calls in this context
            context_id_pattern = rf'getElementById\s*\([\'"]([^\'"]+)[\'"]\)'
            context_id_matches = list(re.finditer(context_id_pattern, chart_init_context))
            
            if context_id_matches:
                # Use the LAST match (closest to Chart initialization)
                context_id_match = context_id_matches[-1]
                found_id = context_id_match.group(1)
                
                logger.debug(f"extract_chart_code: Fallback - Chart init at offset {chart_init.start()} uses ID '{found_id}' (looking for '{chart_id}')")
                
                # CRITICAL: Must be exact match
                if found_id == chart_id:
                    chart_init_match = chart_init
                    logger.info(f"extract_chart_code: ✓ Found correct Chart initialization (fallback) for '{chart_id}' at offset {chart_init.start()}")
                    break
                else:
                    logger.debug(f"extract_chart_code: Fallback - Rejected ID '{found_id}' (not equal to '{chart_id}')")
    
    if not chart_init_match:
        # If no match found, log error with details
        logger.error(f"extract_chart_code: ✗ No Chart initialization found with chart_id '{chart_id}'")
        if 'all_chart_inits' in locals() and all_chart_inits:
            logger.error(f"extract_chart_code: Found {len(all_chart_inits)} Chart initializations but none matched '{chart_id}'")
            for i, chart_init in enumerate(all_chart_inits[:3]):
                lookback_start = max(0, start_pos + chart_init.start() - 150)
                snippet = content[lookback_start:start_pos + chart_init.end() + 50]
                logger.error(f"  Chart init {i+1} snippet: {snippet[:200]}")
            return f"// ERROR: No Chart initialization found for '{chart_id}' (found {len(all_chart_inits)} but none matched)"
        else:
            logger.error(f"extract_chart_code: No Chart initializations found at all for '{chart_id}'")
            return f"// ERROR: No Chart initialization found for '{chart_id}'"
    
    # At this point, chart_init_match is verified to use the correct chart_id
    logger.info(f"extract_chart_code: ✓ Using Chart initialization at offset {chart_init_match.start()} for '{chart_id}'")
    
    # Extract the full chart configuration
    chart_start = start_pos + chart_init_match.start()
    
    # Find the opening brace of the Chart config object
    # The pattern "new Chart(... , {" should have the opening brace right after the comma
    match_text = chart_init_match.group(0)
    chart_config_start = start_pos + chart_init_match.end() - 1
    
    # Find the first opening brace after the Chart initialization
    # Look backwards from end() to find the opening brace
    search_start = start_pos + chart_init_match.end()
    brace_count = 0
    found_opening_brace = False
    
    # First, try to find the opening brace in the matched text itself
    if '{' in match_text:
        # Find the last { in the match (should be the config opening brace)
        last_brace_in_match = match_text.rfind('{')
        if last_brace_in_match >= 0:
            chart_config_start = start_pos + chart_init_match.start() + last_brace_in_match
            brace_count = 1
            found_opening_brace = True
            logger.debug(f"extract_chart_code: Found opening brace in match text at position {chart_config_start}")
    
    # If not found in match, search forward (but skip whitespace and newlines)
    if not found_opening_brace:
        for i in range(search_start, min(len(content), search_start + 500)):
            char = content[i]
            # Skip whitespace, newlines, and comments
            if char in [' ', '\t', '\n', '\r']:
                continue
            if char == '{':
                chart_config_start = i
                brace_count = 1
                found_opening_brace = True
                logger.debug(f"extract_chart_code: Found opening brace after match at position {chart_config_start}")
                break
    
    if not found_opening_brace:
        logger.error(f"extract_chart_code: Could not find opening brace for chart '{chart_id}'")
        logger.error(f"extract_chart_code: Match text: {match_text[:200]}")
        logger.error(f"extract_chart_code: Content after match: {content[search_start:search_start+200]}")
        return f"// ERROR: Could not find opening brace for chart '{chart_id}'"
    
    # Now find the matching closing brace
    in_string = False
    string_char = None
    escaped = False
    chart_end = chart_config_start + 1
    max_search = 50000  # Increased from 10000 to handle larger charts
    
    logger.debug(f"extract_chart_code: Starting brace matching from position {chart_config_start}, brace_count={brace_count}")
    
    # Track positions for debugging when brace_count doesn't reach 0
    brace_history = []
    
    for i in range(chart_config_start + 1, min(len(content), chart_config_start + max_search)):
        char = content[i]
        
        if escaped:
            escaped = False
            continue
        
        if char == '\\':
            escaped = True
            continue
        
        if not in_string and (char == '"' or char == "'"):
            in_string = True
            string_char = char
        elif in_string and char == string_char:
            in_string = False
            string_char = None
        elif not in_string:
            if char == '{':
                brace_count += 1
                if len(brace_history) < 20:  # Keep last 20 brace operations for debugging
                    brace_history.append(('open', i, brace_count))
            elif char == '}':
                brace_count -= 1
                if len(brace_history) < 20:
                    brace_history.append(('close', i, brace_count))
                if brace_count == 0:
                    chart_end = i + 1
                    logger.info(f"extract_chart_code: ✓ Found matching closing brace for '{chart_id}' at position {chart_end}")
                    break
                elif brace_count < 0:
                    # This shouldn't happen if we started correctly
                    logger.warning(f"extract_chart_code: Brace count went negative at position {i} for '{chart_id}'")
                    # Reset and use this position
                    brace_count = 0
                    chart_end = i + 1
                    logger.warning(f"extract_chart_code: Recovered by using position {chart_end} as end")
                    break
    
    if brace_count != 0:
        logger.warning(f"extract_chart_code: Could not find matching closing brace for '{chart_id}' (brace_count={brace_count})")
        logger.warning(f"extract_chart_code: Searched from {chart_config_start} to {chart_config_start + max_search}")
        logger.warning(f"extract_chart_code: Content snippet around start: {content[chart_config_start:chart_config_start+500]}")
        if brace_history:
            logger.warning(f"extract_chart_code: Last brace operations: {brace_history[-10:]}")
        
        # Try alternative method: look for the pattern "});" which typically ends Chart initialization
        # This is more reliable when brace counting fails
        logger.info(f"extract_chart_code: Trying alternative method to find chart end for '{chart_id}'")
        alternative_end = None
        
        # Reset chart_end to a reasonable starting point for alternative search
        # Use the position where we stopped searching (end of max_search range)
        chart_end = min(chart_config_start + max_search, len(content))
        
        # Look for "});" pattern after chart_config_start
        # We need to find the one that belongs to "new Chart(...)" not other functions
        for i in range(chart_config_start + 100, min(len(content), chart_config_start + max_search)):
            if i + 1 < len(content):
                if content[i] == '}' and content[i+1] == ')' and i + 2 < len(content) and content[i+2] == ';':
                    # Verify this is likely the end of our Chart by checking if we're in the right context
                    # Look backwards for "new Chart" pattern
                    lookback_start = max(0, i - 8000)  # Increased lookback range
                    context = content[lookback_start:i+3]
                    
                    # Check if this "});" is preceded by "new Chart" and our chart_id
                    # Pattern: new Chart(...getElementById('chart_id')..., {...});
                    has_new_chart = 'new Chart' in context or 'new Chart(' in context
                    has_chart_id = f"getElementById('{chart_id}')" in context or f'getElementById("{chart_id}")' in context
                    
                    if has_new_chart and has_chart_id:
                        # Additional verification: count braces between chart_start and this position
                        # to ensure we're not picking up a nested function
                        test_content = content[chart_start:i+3]
                        test_brace_count = 0
                        test_in_string = False
                        test_string_char = None
                        test_escaped = False
                        
                        for char in test_content:
                            if test_escaped:
                                test_escaped = False
                                continue
                            if char == '\\':
                                test_escaped = True
                                continue
                            if not test_in_string and (char == '"' or char == "'"):
                                test_in_string = True
                                test_string_char = char
                            elif test_in_string and char == test_string_char:
                                test_in_string = False
                                test_string_char = None
                            elif not test_in_string:
                                if char == '{':
                                    test_brace_count += 1
                                elif char == '}':
                                    test_brace_count -= 1
                        
                        # If brace count is balanced (or close to it), this is likely our end
                        # We expect brace_count to be 0 or 1 (0 if perfectly balanced, 1 if we're counting the closing brace)
                        if test_brace_count <= 1:  # Allow for small discrepancies
                            # Additional check: verify this is not inside a nested function
                            # Look for "new Chart" pattern before this position
                            chart_init_pos = test_content.find('new Chart')
                            if chart_init_pos >= 0:
                                # Count braces from new Chart to this position
                                init_to_end = test_content[chart_init_pos:]
                                init_brace_count = 0
                                init_in_string = False
                                init_string_char = None
                                init_escaped = False
                                
                                for char in init_to_end:
                                    if init_escaped:
                                        init_escaped = False
                                        continue
                                    if char == '\\':
                                        init_escaped = True
                                        continue
                                    if not init_in_string and (char == '"' or char == "'"):
                                        init_in_string = True
                                        init_string_char = char
                                    elif init_in_string and char == init_string_char:
                                        init_in_string = False
                                        init_string_char = None
                                    elif not init_in_string:
                                        if char == '{':
                                            init_brace_count += 1
                                        elif char == '}':
                                            init_brace_count -= 1
                                
                                # If brace count from "new Chart" to "});" is balanced, this is our end
                                # We expect init_brace_count to be 0 or 1 (0 if perfectly balanced, 1 if we're counting the closing brace)
                                if init_brace_count <= 1:
                                    # Additional verification: check that this "});" is immediately after our chart config
                                    # Look for patterns that indicate this is the end of new Chart(...)
                                    # Check if there's a newline or whitespace before the semicolon
                                    if i + 2 < len(content) and content[i+2] == ';':
                                        # Verify the context - should have "new Chart" before and our chart_id
                                        verify_start = max(0, chart_start - 100)
                                        verify_context = content[verify_start:i+3]
                                        if 'new Chart' in verify_context and chart_id in verify_context:
                                            alternative_end = i + 3
                                            logger.info(f"extract_chart_code: ✓ Found alternative end pattern '}});' at position {alternative_end} (test_brace_count={test_brace_count}, init_brace_count={init_brace_count})")
                                            break
                                    else:
                                        # Even if semicolon check fails, if brace count is balanced, use it
                                        # This handles cases where there might be whitespace or comments
                                        if init_brace_count == 0:
                                            alternative_end = i + 3
                                            logger.info(f"extract_chart_code: ✓ Found alternative end pattern '}});' at position {alternative_end} (init_brace_count={init_brace_count}, balanced)")
                                            break
        
        if alternative_end:
            chart_end = alternative_end
            brace_count = 0  # Reset to indicate success
            logger.info(f"extract_chart_code: Using alternative end method, chart_end={chart_end}, length={chart_end - chart_start}")
        else:
            # Last resort: try to find the end of the statement (semicolon or end of line)
            # Search from chart_config_start, not chart_end (which might be too early)
            search_start = chart_config_start + 100
            for i in range(search_start, min(len(content), search_start + 10000)):
                if content[i] == ';':
                    # Check if there's a closing brace and paren before semicolon
                    if i > 2 and content[i-1] == ')' and content[i-2] == '}':
                        # Verify this is likely our chart end by checking context
                        verify_start = max(0, chart_start - 200)
                        verify_context = content[verify_start:i+1]
                        if 'new Chart' in verify_context and chart_id in verify_context:
                            chart_end = i + 1
                            logger.warning(f"extract_chart_code: Using semicolon after '}});' as fallback end at position {chart_end}")
                            break
    
    # Extract the code
    chart_code = content[chart_start:chart_end]
    
    # Verify we got something meaningful
    if len(chart_code) < 20:
        logger.error(f"extract_chart_code: Extracted code too short ({len(chart_code)} chars) for '{chart_id}'")
        logger.error(f"extract_chart_code: chart_start={chart_start}, chart_end={chart_end}")
        logger.error(f"extract_chart_code: Extracted snippet: {chart_code[:200]}")
        return f"// ERROR: Extracted code too short for '{chart_id}' (only {len(chart_code)} characters). Start: {chart_start}, End: {chart_end}"
    
    # Verify the extracted code contains the chart_id
    if chart_id not in chart_code and 'getElementById' in chart_code:
        logger.warning(f"extract_chart_code: Extracted code does not contain chart_id '{chart_id}'")
        logger.warning(f"extract_chart_code: Code snippet: {chart_code[:300]}")
    
    logger.info(f"extract_chart_code: ✓ Successfully extracted {len(chart_code)} characters for '{chart_id}'")
    return chart_code




def apply_changes_to_content(content: str, changes: list) -> str:
    """Apply changes to content (for preview only)"""
    # Sort changes by position (from end to start to preserve positions)
    changes_sorted = sorted(changes, key=lambda x: x[0], reverse=True)
    
    result = content
    for start, end, replacement in changes_sorted:
        result = result[:start] + replacement + result[end:]
    
    return result
