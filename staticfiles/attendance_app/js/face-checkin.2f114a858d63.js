class FaceCheckin {
    constructor(options) {
        this.checkinUrl = options.checkinUrl;
        this.recentUrl = options.recentUrl;
        this.checkinBtn = $(options.checkinBtn);
        this.statusEl = $(options.statusEl);
        this.resultCard = $(options.resultCard);
        this.resultContent = $(options.resultContent);
        this.recentTable = $(options.recentTable);
        
        this.isProcessing = false;
        this.init();
    }
    
    init() {
        this.checkinBtn.on('click', () => this.performCheckin());
        this.loadRecentCheckins();
        
        // Auto-refresh recent checkins every 30 seconds
        setInterval(() => this.loadRecentCheckins(), 30000);
    }
    
    performCheckin() {
        if (this.isProcessing) {
            this.showStatus('Already processing...', 'warning');
            return;
        }
        
        this.isProcessing = true;
        this.checkinBtn.prop('disabled', true);
        this.showStatus('Processing... Please look at the camera', 'info');
        this.resultCard.addClass('d-none');
        
        $.ajax({
            url: this.checkinUrl,
            method: 'POST',
            headers: {
                'X-CSRFToken': this.getCookie('csrftoken')
            },
            success: (response) => {
                if (response.success) {
                    this.showSuccess(response);
                } else {
                    this.showError(response.message);
                }
            },
            error: (xhr) => {
                this.showError('System error. Please try again.');
                console.error('Checkin error:', xhr.responseText);
            },
            complete: () => {
                this.isProcessing = false;
                this.checkinBtn.prop('disabled', false);
                this.loadRecentCheckins();
            }
        });
    }
    
    showSuccess(response) {
        this.statusEl.removeClass('alert-info alert-warning alert-danger')
            .addClass('alert-success')
            .html(`<i class="fas fa-check-circle"></i> Check-in successful!`);
        
        // Build result HTML
        let beltClass = response.member.belt.toLowerCase().split(' ')[0];
        let stripes = '⭐'.repeat(response.member.stripes);
        
        let html = `
            <div class="text-center">
                <i class="fas fa-check-circle fa-4x text-success mb-3"></i>
                <h3>Welcome, ${response.member.name}!</h3>
                <div class="belt-badge belt-${beltClass} my-3">
                    ${response.member.belt} ${stripes}
                </div>
                <p class="mb-2">
                    <strong>Confidence:</strong> ${response.member.confidence}
                </p>
                <p class="text-muted">
                    <i class="fas fa-clock"></i> ${new Date().toLocaleTimeString()}
                </p>
            </div>
        `;
        
        this.resultContent.html(html);
        this.resultCard.removeClass('d-none').addClass('success-card');
        
        // Auto-hide after 5 seconds
        setTimeout(() => {
            this.resultCard.addClass('d-none');
        }, 5000);
    }
    
    showError(message) {
        this.statusEl.removeClass('alert-info alert-success alert-warning')
            .addClass('alert-danger')
            .html(`<i class="fas fa-exclamation-circle"></i> ${message}`);
        
        let html = `
            <div class="text-center">
                <i class="fas fa-times-circle fa-4x text-danger mb-3"></i>
                <h4>Check-in Failed</h4>
                <p>${message}</p>
                <p class="text-muted small">Please try again or use manual check-in</p>
            </div>
        `;
        
        this.resultContent.html(html);
        this.resultCard.removeClass('d-none').addClass('error-card');
        
        // Auto-hide after 3 seconds
        setTimeout(() => {
            this.resultCard.addClass('d-none');
        }, 3000);
    }
    
    showStatus(message, type = 'info') {
        this.statusEl.removeClass('alert-info alert-success alert-warning alert-danger')
            .addClass(`alert-${type}`)
            .html(`<i class="fas fa-${type === 'info' ? 'info-circle' : 'exclamation-circle'}"></i> ${message}`);
    }
    
    loadRecentCheckins() {
        $.get(this.recentUrl, (data) => {
            let html = '';
            data.forEach(checkin => {
                html += `
                    <tr>
                        <td>${checkin.time}</td>
                        <td>${checkin.name}</td>
                        <td><span class="badge bg-${checkin.belt}">${checkin.belt_display}</span></td>
                        <td>${checkin.confidence}</td>
                    </tr>
                `;
            });
            
            if (html === '') {
                html = '<tr><td colspan="4" class="text-center text-muted">No recent face check-ins</td></tr>';
            }
            
            this.recentTable.html(html);
        });
    }
    
    getCookie(name) {
        let cookieValue = null;
        if (document.cookie && document.cookie !== '') {
            const cookies = document.cookie.split(';');
            for (let i = 0; i < cookies.length; i++) {
                const cookie = cookies[i].trim();
                if (cookie.substring(0, name.length + 1) === (name + '=')) {
                    cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                    break;
                }
            }
        }
        return cookieValue;
    }
}