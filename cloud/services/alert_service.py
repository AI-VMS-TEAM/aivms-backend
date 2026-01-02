"""
Alert Service
Filters noise and sends meaningful alerts via email, webhook, etc.
"""

import os
import logging
import json
import smtplib
import requests
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Callable
from collections import defaultdict
import threading

logger = logging.getLogger(__name__)


class AlertService:
    """
    Processes events and generates meaningful alerts.
    Features:
    - Alert rules (filters)
    - Rate limiting (cooldowns)
    - Multiple notification channels (email, webhook, push)
    - Alert batching
    """
    
    def __init__(self, event_service, config):
        self.event_service = event_service
        self.config = config
        
        # Alert cooldowns to prevent spam
        # Key: (tenant_id, alert_type, camera_id) -> last_alert_time
        self._cooldowns: Dict[tuple, datetime] = {}
        self._cooldown_lock = threading.Lock()
        
        # Alert rules per tenant
        # Key: tenant_id -> list of rules
        self._rules: Dict[str, List[Dict]] = defaultdict(list)
        
        # Notification handlers
        self._handlers: Dict[str, Callable] = {
            'email': self._send_email,
            'webhook': self._send_webhook,
            'log': self._log_alert
        }
        
        logger.info("✅ Alert service initialized")
    
    def process_detection(self, detection: Dict) -> Optional[Dict]:
        """Process a detection event and potentially create an alert."""
        tenant_id = detection.get('tenant_id')
        
        # Check against rules
        rules = self._rules.get(tenant_id, [])
        
        for rule in rules:
            if self._matches_rule(detection, rule):
                return self._create_alert_from_detection(detection, rule)
        
        # Default: alert on high-confidence person detection
        if detection.get('object_class') == 'person' and detection.get('confidence', 0) > 0.8:
            return self._create_alert_from_detection(detection, {
                'alert_type': 'person_detected',
                'severity': 'info',
                'title': 'Person Detected'
            })
        
        return None
    
    def process_zone_event(self, zone_event: Dict) -> Optional[Dict]:
        """Process a zone event and potentially create an alert."""
        tenant_id = zone_event.get('tenant_id')
        event_type = zone_event.get('event_type')
        
        # Always alert on zone enter/exit
        if event_type in ('enter', 'exit'):
            return self._create_alert_from_zone(zone_event)
        
        # Alert on dwell time threshold
        if event_type == 'dwell' and zone_event.get('dwell_time', 0) > 60:
            return self._create_alert_from_zone(zone_event, severity='warning')
        
        return None
    
    def _matches_rule(self, event: Dict, rule: Dict) -> bool:
        """Check if event matches a rule."""
        # Object class filter
        if 'object_classes' in rule:
            if event.get('object_class') not in rule['object_classes']:
                return False
        
        # Confidence threshold
        if 'min_confidence' in rule:
            if event.get('confidence', 0) < rule['min_confidence']:
                return False
        
        # Camera filter
        if 'camera_ids' in rule:
            if event.get('camera_id') not in rule['camera_ids']:
                return False
        
        # Zone filter
        if 'zone_ids' in rule:
            if event.get('zone_id') not in rule['zone_ids']:
                return False
        
        # Time window
        if 'time_window' in rule:
            now = datetime.now()
            start = rule['time_window'].get('start')
            end = rule['time_window'].get('end')
            if start and end:
                current_time = now.strftime('%H:%M')
                if not (start <= current_time <= end):
                    return False
        
        return True
    
    def _create_alert_from_detection(self, detection: Dict, rule: Dict) -> Optional[Dict]:
        """Create alert from detection event."""
        tenant_id = detection.get('tenant_id')
        alert_type = rule.get('alert_type', 'detection')
        camera_id = detection.get('camera_id')
        
        # Check cooldown
        if not self._check_cooldown(tenant_id, alert_type, camera_id):
            return None
        
        alert_data = {
            'tenant_id': tenant_id,
            'edge_id': detection.get('edge_id'),
            'camera_id': camera_id,
            'alert_type': alert_type,
            'severity': rule.get('severity', 'info'),
            'title': rule.get('title', f"{detection.get('object_class', 'Object')} detected"),
            'description': f"Detected {detection.get('object_class')} with {detection.get('confidence', 0):.1%} confidence",
            'event_id': detection.get('id'),
            'timestamp': detection.get('timestamp'),
            'metadata': {
                'object_class': detection.get('object_class'),
                'confidence': detection.get('confidence'),
                'bbox': detection.get('bbox')
            }
        }
        
        # Store alert
        alert_id = self.event_service.create_alert(alert_data)
        if alert_id:
            alert_data['id'] = alert_id
            self._send_notifications(alert_data)
            return alert_data
        
        return None
    
    def _create_alert_from_zone(self, zone_event: Dict, severity: str = 'info') -> Optional[Dict]:
        """Create alert from zone event."""
        tenant_id = zone_event.get('tenant_id')
        event_type = zone_event.get('event_type')
        zone_name = zone_event.get('zone_name', 'Unknown Zone')
        camera_id = zone_event.get('camera_id')
        alert_type = f'zone_{event_type}'
        
        # Check cooldown
        if not self._check_cooldown(tenant_id, alert_type, camera_id):
            return None
        
        if event_type == 'enter':
            title = f"Zone Entry: {zone_name}"
            description = f"{zone_event.get('object_class', 'Object')} entered {zone_name}"
        elif event_type == 'exit':
            title = f"Zone Exit: {zone_name}"
            description = f"{zone_event.get('object_class', 'Object')} exited {zone_name}"
        elif event_type == 'dwell':
            title = f"Extended Dwell: {zone_name}"
            description = f"{zone_event.get('object_class', 'Object')} in {zone_name} for {zone_event.get('dwell_time', 0):.0f}s"
            severity = 'warning'
        else:
            title = f"Zone Event: {zone_name}"
            description = f"{event_type} in {zone_name}"
        
        alert_data = {
            'tenant_id': tenant_id,
            'edge_id': zone_event.get('edge_id'),
            'camera_id': camera_id,
            'alert_type': alert_type,
            'severity': severity,
            'title': title,
            'description': description,
            'event_id': zone_event.get('id'),
            'timestamp': zone_event.get('timestamp'),
            'metadata': {
                'zone_id': zone_event.get('zone_id'),
                'zone_name': zone_name,
                'object_class': zone_event.get('object_class'),
                'dwell_time': zone_event.get('dwell_time')
            }
        }
        
        # Store alert
        alert_id = self.event_service.create_alert(alert_data)
        if alert_id:
            alert_data['id'] = alert_id
            self._send_notifications(alert_data)
            return alert_data
        
        return None
    
    def _check_cooldown(self, tenant_id: str, alert_type: str, camera_id: str) -> bool:
        """Check if we're in cooldown period for this alert type."""
        key = (tenant_id, alert_type, camera_id)
        cooldown_seconds = self.config.get('alert_cooldown_seconds', 60)
        
        with self._cooldown_lock:
            last_alert = self._cooldowns.get(key)
            now = datetime.now()
            
            if last_alert and (now - last_alert).total_seconds() < cooldown_seconds:
                return False
            
            self._cooldowns[key] = now
            return True
    
    def _send_notifications(self, alert: Dict):
        """Send notifications for an alert."""
        tenant_id = alert.get('tenant_id')
        
        # Get notification settings for tenant
        # For now, just log
        self._handlers['log'](alert)
        
        # Check if email is configured
        if self.config.get('smtp_host'):
            # In production, get email from tenant settings
            pass
        
        # Check if webhook is configured
        webhook_url = self.config.get('webhook_url')
        if webhook_url:
            try:
                self._handlers['webhook'](alert, webhook_url)
            except Exception as e:
                logger.error(f"Failed to send webhook: {e}")
    
    def _log_alert(self, alert: Dict):
        """Log alert to console."""
        severity = alert.get('severity', 'info')
        if severity == 'critical':
            logger.critical(f"🚨 ALERT: {alert.get('title')} - {alert.get('description')}")
        elif severity == 'warning':
            logger.warning(f"⚠️ ALERT: {alert.get('title')} - {alert.get('description')}")
        else:
            logger.info(f"📢 ALERT: {alert.get('title')} - {alert.get('description')}")
    
    def _send_email(self, alert: Dict, email_config: Dict):
        """Send alert via email."""
        try:
            msg = MIMEMultipart('alternative')
            msg['Subject'] = f"[AIVMS Alert] {alert.get('title')}"
            msg['From'] = email_config.get('from_email')
            msg['To'] = email_config.get('to_email')
            
            # Plain text version
            text = f"""
            Alert: {alert.get('title')}
            
            {alert.get('description')}
            
            Time: {alert.get('timestamp')}
            Severity: {alert.get('severity')}
            Camera: {alert.get('camera_id')}
            """
            
            # HTML version
            html = f"""
            <html>
            <body>
                <h2>{alert.get('title')}</h2>
                <p>{alert.get('description')}</p>
                <table>
                    <tr><td><strong>Time:</strong></td><td>{alert.get('timestamp')}</td></tr>
                    <tr><td><strong>Severity:</strong></td><td>{alert.get('severity')}</td></tr>
                    <tr><td><strong>Camera:</strong></td><td>{alert.get('camera_id')}</td></tr>
                </table>
            </body>
            </html>
            """
            
            msg.attach(MIMEText(text, 'plain'))
            msg.attach(MIMEText(html, 'html'))
            
            # Send email
            with smtplib.SMTP(email_config.get('smtp_host'), email_config.get('smtp_port', 587)) as server:
                server.starttls()
                server.login(email_config.get('smtp_user'), email_config.get('smtp_password'))
                server.sendmail(msg['From'], [msg['To']], msg.as_string())
            
            logger.info(f"📧 Email sent for alert: {alert.get('title')}")
        except Exception as e:
            logger.error(f"Failed to send email: {e}")
    
    def _send_webhook(self, alert: Dict, webhook_url: str):
        """Send alert via webhook."""
        try:
            response = requests.post(
                webhook_url,
                json={
                    'type': 'alert',
                    'alert': alert
                },
                headers={'Content-Type': 'application/json'},
                timeout=10
            )
            response.raise_for_status()
            logger.info(f"🔗 Webhook sent for alert: {alert.get('title')}")
        except Exception as e:
            logger.error(f"Failed to send webhook: {e}")
    
    # ==========================================
    # Rule Management
    # ==========================================
    
    def add_rule(self, tenant_id: str, rule: Dict) -> str:
        """Add an alert rule for a tenant."""
        import secrets
        rule_id = f"rule_{secrets.token_hex(6)}"
        rule['id'] = rule_id
        self._rules[tenant_id].append(rule)
        logger.info(f"✅ Added alert rule for tenant {tenant_id}: {rule.get('name', rule_id)}")
        return rule_id
    
    def remove_rule(self, tenant_id: str, rule_id: str) -> bool:
        """Remove an alert rule."""
        rules = self._rules.get(tenant_id, [])
        for i, rule in enumerate(rules):
            if rule.get('id') == rule_id:
                rules.pop(i)
                logger.info(f"✅ Removed alert rule: {rule_id}")
                return True
        return False
    
    def get_rules(self, tenant_id: str) -> List[Dict]:
        """Get all rules for a tenant."""
        return self._rules.get(tenant_id, [])
    
    def set_rules(self, tenant_id: str, rules: List[Dict]):
        """Set all rules for a tenant."""
        for rule in rules:
            if 'id' not in rule:
                import secrets
                rule['id'] = f"rule_{secrets.token_hex(6)}"
        self._rules[tenant_id] = rules
