#!/bin/bash

# BJJ Attendance System Installation Script for Raspberry Pi

echo "========================================="
echo "BJJ Attendance System Installation"
echo "========================================="

# Check if running as root
if [ "$EUID" -ne 0 ]; then 
    echo "Please run as root (sudo ./install.sh)"
    exit 1
fi

# Update system
echo "Updating system packages..."
apt-get update
apt-get upgrade -y

# Install system dependencies
echo "Installing system dependencies..."
apt-get install -y python3-pip python3-venv
apt-get install -y libatlas-base-dev libhdf5-dev
apt-get install -y libopencv-dev python3-opencv
apt-get install -y cmake build-essential
apt-get install -y redis-server
apt-get install -y nginx
apt-get install -y sqlite3

# Enable camera interface
echo "Enabling camera interface..."
raspi-config nonint do_camera 0

# Create user and directories
echo "Creating application directories..."
useradd -m -s /bin/bash bjjattendance || true
mkdir -p /opt/bjj_attendance
mkdir -p /var/log/bjj_attendance
mkdir -p /var/lib/bjj_attendance/data
mkdir -p /var/lib/bjj_attendance/media
mkdir -p /var/lib/bjj_attendance/static

# Set permissions
chown -R bjjattendance:bjjattendance /opt/bjj_attendance
chown -R bjjattendance:bjjattendance /var/log/bjj_attendance
chown -R bjjattendance:bjjattendance /var/lib/bjj_attendance

# Copy application files
echo "Copying application files..."
cp -r ../* /opt/bjj_attendance/
chown -R bjjattendance:bjjattendance /opt/bjj_attendance/

# Create virtual environment
echo "Creating Python virtual environment..."
su - bjjattendance -c "cd /opt/bjj_attendance && python3 -m venv venv"

# Install Python packages
echo "Installing Python packages..."
su - bjjattendance -c "cd /opt/bjj_attendance && source venv/bin/activate && pip install --upgrade pip"
su - bjjattendance -c "cd /opt/bjj_attendance && source venv/bin/activate && pip install -r requirements.txt"

# Initialize database
echo "Initializing database..."
su - bjjattendance -c "cd /opt/bjj_attendance && source venv/bin/activate && python manage.py migrate"
su - bjjattendance -c "cd /opt/bjj_attendance && source venv/bin/activate && python manage.py collectstatic --noinput"

# Create superuser (optional)
echo "Creating admin user..."
su - bjjattendance -c "cd /opt/bjj_attendance && source venv/bin/activate && python manage.py createsuperuser"

# Setup systemd service
echo "Creating systemd service..."
cp /opt/bjj_attendance/scripts/bjj-attendance.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable bjj-attendance.service
systemctl start bjj-attendance.service

# Setup nginx
echo "Configuring nginx..."
cp /opt/bjj_attendance/scripts/nginx.conf /etc/nginx/sites-available/bjj_attendance
ln -s /etc/nginx/sites-available/bjj_attendance /etc/nginx/sites-enabled/
systemctl restart nginx

# Setup cron jobs for auto-sync
echo "Setting up cron jobs..."
echo "0 */6 * * * bjjattendance cd /opt/bjj_attendance && source venv/bin/activate && python manage.py sync_members" >> /etc/crontab
echo "*/5 * * * * bjjattendance cd /opt/bjj_attendance && source venv/bin/activate && python manage.py sync_attendance" >> /etc/crontab

# Create backup script
echo "Creating backup script..."
cat > /usr/local/bin/backup_bjj_attendance << 'EOF'
#!/bin/bash
BACKUP_DIR="/var/backups/bjj_attendance"
mkdir -p $BACKUP_DIR
DATE=$(date +%Y%m%d_%H%M%S)
sqlite3 /var/lib/bjj_attendance/data/attendance.db ".backup '$BACKUP_DIR/attendance_$DATE.db'"
tar -czf "$BACKUP_DIR/media_$DATE.tar.gz" -C /var/lib/bjj_attendance media
find $BACKUP_DIR -name "*.db" -mtime +30 -delete
find $BACKUP_DIR -name "*.tar.gz" -mtime +30 -delete
EOF
chmod +x /usr/local/bin/backup_bjj_attendance

# Add to daily cron
echo "0 2 * * * root /usr/local/bin/backup_bjj_attendance" >> /etc/crontab

# Get IP address
IP_ADDR=$(hostname -I | awk '{print $1}')

echo "========================================="
echo "Installation Complete!"
echo "========================================="
echo ""
echo "Access the application at:"
echo "  http://$IP_ADDR"
echo "  http://$(hostname).local (if mDNS is enabled)"
echo ""
echo "Default login:"
echo "  Username: admin"
echo "  Password: (what you set during installation)"
echo ""
echo "Service management:"
echo "  sudo systemctl start|stop|restart bjj-attendance"
echo "  sudo journalctl -u bjj-attendance -f"
echo ""
echo "Backup location: /var/backups/bjj_attendance/"
echo "Logs location: /var/log/bjj_attendance/"
echo ""
echo "========================================="