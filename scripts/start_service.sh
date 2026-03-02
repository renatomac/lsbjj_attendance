[Unit]
Description=BJJ Attendance System
After=network.target redis-server.service
Wants=redis-server.service

[Service]
Type=simple
User=bjjattendance
Group=bjjattendance
WorkingDirectory=/opt/bjj_attendance
Environment="PATH=/opt/bjj_attendance/venv/bin"
Environment="DJANGO_SETTINGS_MODULE=attendance_project.settings"
ExecStart=/opt/bjj_attendance/venv/bin/gunicorn attendance_project.wsgi:application \
          --bind 127.0.0.1:8000 \
          --workers 2 \
          --threads 4 \
          --worker-class sync \
          --timeout 120 \
          --access-logfile /var/log/bjj_attendance/access.log \
          --error-logfile /var/log/bjj_attendance/error.log
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target