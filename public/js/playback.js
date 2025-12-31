/**
 * Playback Player - Main JavaScript
 * Handles video playback, timeline scrubbing, and controls
 */

class PlaybackPlayer {
    constructor() {
        this.video = document.getElementById('videoPlayer');
        this.hls = null;
        this.currentCamera = null;
        this.playbackInfo = null;
        this.timelineData = null;
        
        this.initializeElements();
        this.attachEventListeners();
        this.loadCameras();
        this.setDefaultDates();
    }
    
    initializeElements() {
        this.elements = {
            cameraSelector: document.getElementById('cameraSelector'),
            startDate: document.getElementById('startDate'),
            startTime: document.getElementById('startTime'),
            endDate: document.getElementById('endDate'),
            endTime: document.getElementById('endTime'),
            btnLoadPlayback: document.getElementById('btnLoadPlayback'),
            btnPlay: document.getElementById('btnPlay'),
            btnPause: document.getElementById('btnPause'),
            btnStop: document.getElementById('btnStop'),
            speedControl: document.getElementById('speedControl'),
            currentTime: document.getElementById('currentTime'),
            duration: document.getElementById('duration'),
            timelineScrubber: document.getElementById('timelineScrubber'),
            playhead: document.getElementById('playhead'),
            videoLoading: document.getElementById('videoLoading'),
            infoSegments: document.getElementById('infoSegments'),
            infoDuration: document.getElementById('infoDuration'),
            infoSize: document.getElementById('infoSize'),
            presetLastHour: document.getElementById('presetLastHour'),
            presetLast24h: document.getElementById('presetLast24h'),
            presetLast7d: document.getElementById('presetLast7d')
        };
    }
    
    attachEventListeners() {
        // Playback controls
        this.elements.btnPlay.addEventListener('click', () => this.video.play());
        this.elements.btnPause.addEventListener('click', () => this.video.pause());
        this.elements.btnStop.addEventListener('click', () => this.stopPlayback());
        this.elements.speedControl.addEventListener('change', (e) => {
            this.video.playbackRate = parseFloat(e.target.value);
        });
        
        // Load playback
        this.elements.btnLoadPlayback.addEventListener('click', () => this.loadPlayback());
        
        // Quick presets
        this.elements.presetLastHour.addEventListener('click', () => this.setPreset('hour'));
        this.elements.presetLast24h.addEventListener('click', () => this.setPreset('day'));
        this.elements.presetLast7d.addEventListener('click', () => this.setPreset('week'));
        
        // Timeline scrubber
        this.elements.timelineScrubber.addEventListener('click', (e) => this.handleTimelineClick(e));
        
        // Video events
        this.video.addEventListener('timeupdate', () => this.updateTimeDisplay());
        this.video.addEventListener('loadedmetadata', () => this.updateDurationDisplay());
        this.video.addEventListener('play', () => this.updatePlayhead());
        this.video.addEventListener('pause', () => this.updatePlayhead());
    }
    
    setDefaultDates() {
        const now = new Date();
        const yesterday = new Date(now.getTime() - 24 * 60 * 60 * 1000);

        // Set dates using local time (not UTC)
        this.setDateInputValue(this.elements.startDate, yesterday);
        this.elements.startTime.value = '00:00';
        this.setDateInputValue(this.elements.endDate, now);
        this.elements.endTime.value = now.toTimeString().slice(0, 5);
    }
    
    async loadCameras() {
        try {
            const response = await fetch('/api/cameras');
            const cameras = await response.json();

            // Check if camera name is passed in URL parameter
            const urlParams = new URLSearchParams(window.location.search);
            const cameraNameFromUrl = urlParams.get('camera');

            this.elements.cameraSelector.innerHTML = '';
            cameras.forEach(cam => {
                const option = document.createElement('option');
                const cameraId = cam.name.toLowerCase().replace(/ /g, '_').replace(/-/g, '_');
                option.value = cameraId;
                option.textContent = cam.name;
                this.elements.cameraSelector.appendChild(option);
            });

            // If camera name was passed in URL, select it
            if (cameraNameFromUrl) {
                const cameraIdFromUrl = cameraNameFromUrl.toLowerCase().replace(/ /g, '_').replace(/-/g, '_');
                const matchingOption = Array.from(this.elements.cameraSelector.options).find(
                    opt => opt.value === cameraIdFromUrl
                );
                if (matchingOption) {
                    this.elements.cameraSelector.value = cameraIdFromUrl;
                    this.currentCamera = cameraIdFromUrl;
                    console.log(`✅ Auto-selected camera from URL: ${cameraNameFromUrl}`);
                }
            } else if (cameras.length > 0) {
                this.currentCamera = this.elements.cameraSelector.value;
            }
        } catch (error) {
            console.error('Failed to load cameras:', error);
            this.elements.cameraSelector.innerHTML = '<option value="">Error loading cameras</option>';
        }
    }
    
    setPreset(preset) {
        const now = new Date();
        let startDate;

        switch (preset) {
            case 'hour':
                startDate = new Date(now.getTime() - 60 * 60 * 1000);
                break;
            case 'day':
                startDate = new Date(now.getTime() - 24 * 60 * 60 * 1000);
                break;
            case 'week':
                startDate = new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000);
                break;
        }

        // Set dates using local time (not UTC)
        // valueAsDate treats the date as UTC, so we need to format it manually
        this.setDateInputValue(this.elements.startDate, startDate);
        this.elements.startTime.value = startDate.toTimeString().slice(0, 5);
        this.setDateInputValue(this.elements.endDate, now);
        this.elements.endTime.value = now.toTimeString().slice(0, 5);
    }

    setDateInputValue(dateInput, date) {
        /**
         * Set date input value using local time (not UTC)
         * valueAsDate treats the date as UTC, which causes day shifts
         * So we format it manually as YYYY-MM-DD
         */
        const year = date.getFullYear();
        const month = String(date.getMonth() + 1).padStart(2, '0');
        const day = String(date.getDate()).padStart(2, '0');
        dateInput.value = `${year}-${month}-${day}`;
    }
    
    async loadPlayback() {
        const camera = this.elements.cameraSelector.value;
        if (!camera) {
            alert('Please select a camera');
            return;
        }
        
        const startDateTime = this.getDateTime(this.elements.startDate, this.elements.startTime);
        const endDateTime = this.getDateTime(this.elements.endDate, this.elements.endTime);
        
        if (!startDateTime || !endDateTime) {
            alert('Please set valid date and time');
            return;
        }
        
        if (startDateTime >= endDateTime) {
            alert('Start time must be before end time');
            return;
        }
        
        this.currentCamera = camera;
        this.showLoading(true);
        
        try {
            // Get playback info
            // Convert to local ISO string (not UTC) to match recording times
            // Recordings are stored in local time, not UTC
            const startTimeStr = this.toLocalISOString(startDateTime);
            const endTimeStr = this.toLocalISOString(endDateTime);
            const url = `/api/playback/${camera}?start_time=${startTimeStr}&end_time=${endTimeStr}`;

            console.log('Loading playback:', {
                camera,
                startTime: startTimeStr,
                endTime: endTimeStr,
                url
            });

            const response = await fetch(url);

            console.log('Playback info response:', response.status, response.statusText);

            if (!response.ok) {
                const errorText = await response.text();
                console.error('Error response:', errorText);
                throw new Error(`HTTP ${response.status}: ${errorText}`);
            }

            this.playbackInfo = await response.json();

            console.log('Playback info received:', {
                segments: this.playbackInfo.segment_count,
                playlistUrl: this.playbackInfo.playlist_url
            });

            if (this.playbackInfo.error) {
                alert('Error: ' + this.playbackInfo.error);
                this.showLoading(false);
                return;
            }

            // Update info display
            this.updateInfoDisplay();

            // Load HLS stream
            this.loadHLSStream(this.playbackInfo.playlist_url);

            // Build timeline
            this.buildTimeline();

        } catch (error) {
            console.error('Failed to load playback:', error);
            alert('Failed to load playback: ' + error.message);
            this.showLoading(false);
        }
    }
    
    getDateTime(dateInput, timeInput) {
        if (!dateInput.value || !timeInput.value) return null;
        
        const dateStr = dateInput.value;
        const timeStr = timeInput.value;
        const dateTime = new Date(`${dateStr}T${timeStr}:00`);
        
        return isNaN(dateTime.getTime()) ? null : dateTime;
    }
    
    loadHLSStream(playlistUrl) {
        console.log('loadHLSStream called with:', playlistUrl);

        if (!playlistUrl) {
            alert('No playlist URL available');
            this.showLoading(false);
            return;
        }

        try {
            if (this.hls) {
                this.hls.destroy();
            }

            if (Hls.isSupported()) {
                console.log('HLS.js is supported, creating new instance');

                // Calculate correct duration from API
                const correctDurationSec = this.playbackInfo.total_duration_ms / 1000;

                this.hls = new Hls({
                    debug: true,
                    enableWorker: true,
                    lowLatencyMode: false,
                    // CRITICAL: Set buffer limits based on actual duration
                    // MediaMTX creates fMP4 files with accumulated duration metadata
                    // HLS.js reads this wrong duration and tries to buffer too much
                    // We limit buffering to the actual duration to prevent stalls
                    maxBufferLength: Math.min(correctDurationSec, 60),
                    maxMaxBufferLength: Math.min(correctDurationSec + 10, 70),
                    maxBufferSize: 100 * 1000 * 1000, // 100MB
                    maxBufferHole: 0.5,
                    // Use EXTINF values from playlist, not file duration
                    startLevel: 0
                });

                this.hls.on(Hls.Events.ERROR, (event, data) => {
                    console.error('HLS Error:', event, data);

                    // Log buffer stall errors separately
                    if (data.details === 'bufferNudgeOnStall') {
                        console.warn('Buffer stall detected - HLS.js is trying to nudge the buffer');
                        console.warn('This usually means the video duration is wrong');
                        console.warn('Expected duration:', this.playbackInfo.total_duration_ms / 1000, 'seconds');
                        console.warn('Actual video duration:', this.video.duration, 'seconds');
                    }

                    if (data.fatal) {
                        switch(data.type) {
                            case Hls.ErrorTypes.NETWORK_ERROR:
                                console.error('Network error, retrying...');
                                this.hls.startLoad();
                                break;
                            case Hls.ErrorTypes.MEDIA_ERROR:
                                console.error('Media error, recovering...');
                                this.hls.recoverMediaError();
                                break;
                            default:
                                this.showLoading(false);
                                alert('Failed to load video stream: ' + data.reason);
                                break;
                        }
                    }
                });

                console.log('Loading source:', playlistUrl);
                this.hls.loadSource(playlistUrl);
                this.hls.attachMedia(this.video);

                // Add timeout to detect if MANIFEST_PARSED never fires
                const manifestTimeout = setTimeout(() => {
                    console.error('MANIFEST_PARSED event did not fire within 10 seconds');
                    this.showLoading(false);
                    alert('Failed to load video: Manifest parsing timeout');
                }, 10000);

                this.hls.on(Hls.Events.MANIFEST_PARSED, () => {
                    clearTimeout(manifestTimeout);
                    console.log('HLS stream loaded successfully');
                    console.log('Video duration from MP4:', this.video.duration, 'seconds');
                    console.log('Correct duration from API:', this.playbackInfo.total_duration_ms / 1000, 'seconds');

                    // NOTE: Cannot override video.duration (read-only property)
                    // Instead, we'll use the correct duration from API in the display
                    // Update duration display with correct value from API
                    this.updateDurationDisplay();

                    this.showLoading(false);

                    // Don't autoplay - let user click play button
                    // this.video.play().catch(e => {
                    //     console.warn('Autoplay prevented:', e);
                    // });
                });
            } else if (this.video.canPlayType('application/vnd.apple.mpegurl')) {
                console.log('Using native HLS support');
                this.video.src = playlistUrl;
                this.showLoading(false);
                this.video.play().catch(e => {
                    console.warn('Autoplay prevented:', e);
                });
            } else {
                alert('HLS streaming not supported in this browser');
                this.showLoading(false);
            }
        } catch (error) {
            console.error('Failed to load HLS stream:', error);
            alert('Failed to load video stream: ' + error.message);
            this.showLoading(false);
        }
    }
    
    buildTimeline() {
        if (!this.playbackInfo || !this.playbackInfo.segments) return;
        
        const scrubber = this.elements.timelineScrubber;
        const buckets = {};
        
        // Group segments by hour
        this.playbackInfo.segments.forEach(seg => {
            const date = new Date(seg.start_time);
            const hour = date.getHours();
            const key = `${hour}:00`;
            
            if (!buckets[key]) {
                buckets[key] = { count: 0, hasMotion: false };
            }
            buckets[key].count++;
        });
        
        // Clear existing buckets
        scrubber.querySelectorAll('.timeline-bucket').forEach(b => b.remove());
        
        // Create buckets
        const bucketCount = Object.keys(buckets).length || 24;
        Object.entries(buckets).forEach(([hour, data]) => {
            const bucket = document.createElement('div');
            bucket.className = 'timeline-bucket' + (data.hasMotion ? ' has-motion' : '');
            bucket.style.flex = '1';
            bucket.title = `${hour} - ${data.count} segments`;
            scrubber.appendChild(bucket);
        });
        
        // Re-add playhead
        scrubber.appendChild(this.elements.playhead);
    }
    
    handleTimelineClick(e) {
        // Use correct duration from API for seeking
        let duration = this.video.duration;
        if (this.playbackInfo && this.playbackInfo.total_duration_ms) {
            duration = this.playbackInfo.total_duration_ms / 1000;
        }

        if (!duration) return;

        const rect = this.elements.timelineScrubber.getBoundingClientRect();
        const percent = (e.clientX - rect.left) / rect.width;
        this.video.currentTime = percent * duration;
    }
    
    updateTimeDisplay() {
        this.elements.currentTime.textContent = this.formatTime(this.video.currentTime);
        this.updatePlayhead();
    }
    
    updateDurationDisplay() {
        // Use correct duration from API, not from video element
        // (video.duration may be wrong due to overlapping segments)
        if (this.playbackInfo && this.playbackInfo.total_duration_ms) {
            const correctDuration = this.playbackInfo.total_duration_ms / 1000;
            this.elements.duration.textContent = this.formatTime(correctDuration);
        } else {
            this.elements.duration.textContent = this.formatTime(this.video.duration);
        }
    }

    updatePlayhead() {
        // Use correct duration from API for playhead positioning
        let duration = this.video.duration;
        if (this.playbackInfo && this.playbackInfo.total_duration_ms) {
            duration = this.playbackInfo.total_duration_ms / 1000;
        }

        if (!duration) return;
        const percent = (this.video.currentTime / duration) * 100;
        this.elements.playhead.style.left = percent + '%';
    }
    
    updateInfoDisplay() {
        if (!this.playbackInfo) return;
        
        this.elements.infoSegments.textContent = this.playbackInfo.segment_count || '-';
        this.elements.infoDuration.textContent = this.formatDuration(this.playbackInfo.total_duration_ms);
        this.elements.infoSize.textContent = this.formatBytes(this.playbackInfo.total_size_bytes);
    }
    
    toLocalISOString(date) {
        /**
         * Convert date to ISO string in LOCAL time (not UTC)
         * Recordings are stored in local time, so we need to send local time to the API
         *
         * Example: 2025-11-12 18:00:00 local time -> "2025-11-12T18:00:00.000"
         * NOT "2025-11-13T00:00:00.000" (UTC)
         */
        const year = date.getFullYear();
        const month = String(date.getMonth() + 1).padStart(2, '0');
        const day = String(date.getDate()).padStart(2, '0');
        const hours = String(date.getHours()).padStart(2, '0');
        const minutes = String(date.getMinutes()).padStart(2, '0');
        const seconds = String(date.getSeconds()).padStart(2, '0');
        const ms = String(date.getMilliseconds()).padStart(3, '0');

        return `${year}-${month}-${day}T${hours}:${minutes}:${seconds}.${ms}`;
    }

    formatTime(seconds) {
        if (!seconds || isNaN(seconds)) return '00:00:00';

        const hours = Math.floor(seconds / 3600);
        const minutes = Math.floor((seconds % 3600) / 60);
        const secs = Math.floor(seconds % 60);

        return `${String(hours).padStart(2, '0')}:${String(minutes).padStart(2, '0')}:${String(secs).padStart(2, '0')}`;
    }
    
    formatDuration(ms) {
        if (!ms) return '-';
        const seconds = Math.floor(ms / 1000);
        const hours = Math.floor(seconds / 3600);
        const minutes = Math.floor((seconds % 3600) / 60);
        return `${hours}h ${minutes}m`;
    }
    
    formatBytes(bytes) {
        if (!bytes) return '-';
        const gb = (bytes / (1024 * 1024 * 1024)).toFixed(2);
        return `${gb} GB`;
    }
    
    showLoading(show) {
        this.elements.videoLoading.style.display = show ? 'flex' : 'none';
    }
    
    stopPlayback() {
        this.video.pause();
        this.video.currentTime = 0;
        if (this.hls) {
            this.hls.destroy();
            this.hls = null;
        }
        this.video.src = '';
    }
}

// Initialize player when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    window.playbackPlayer = new PlaybackPlayer();
});

