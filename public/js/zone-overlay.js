/**
 * Zone Overlay Visualization
 * Draws zones and detections on top of video streams
 */

class ZoneOverlay {
    constructor(videoElement, canvasElement) {
        this.video = videoElement;
        this.canvas = canvasElement;
        this.ctx = canvasElement.getContext('2d');
        this.zones = [];
        this.tracks = [];
        this.animationId = null;
        
        // Resize canvas to match video
        this.resizeCanvas();
        window.addEventListener('resize', () => this.resizeCanvas());
    }
    
    resizeCanvas() {
        if (this.video.videoWidth > 0) {
            this.canvas.width = this.video.videoWidth;
            this.canvas.height = this.video.videoHeight;
        }
    }
    
    setZones(zones) {
        this.zones = zones;
    }
    
    setTracks(tracks) {
        this.tracks = tracks;
    }
    
    hexToRgb(hex) {
        const result = /^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(hex);
        return result ? {
            r: parseInt(result[1], 16),
            g: parseInt(result[2], 16),
            b: parseInt(result[3], 16)
        } : { r: 255, g: 255, b: 255 };
    }
    
    drawZones() {
        this.zones.forEach(zone => {
            const polygon = zone.polygon;
            if (!polygon || polygon.length < 3) return;
            
            const color = this.hexToRgb(zone.color);
            const rgbaFill = `rgba(${color.r}, ${color.g}, ${color.b}, 0.2)`;
            const rgbaStroke = `rgba(${color.r}, ${color.g}, ${color.b}, 0.8)`;
            
            // Draw filled polygon
            this.ctx.fillStyle = rgbaFill;
            this.ctx.strokeStyle = rgbaStroke;
            this.ctx.lineWidth = 2;
            
            this.ctx.beginPath();
            this.ctx.moveTo(polygon[0][0], polygon[0][1]);
            for (let i = 1; i < polygon.length; i++) {
                this.ctx.lineTo(polygon[i][0], polygon[i][1]);
            }
            this.ctx.closePath();
            this.ctx.fill();
            this.ctx.stroke();
            
            // Draw zone label
            if (polygon.length > 0) {
                this.ctx.fillStyle = rgbaStroke;
                this.ctx.font = 'bold 16px Arial';
                this.ctx.fillText(zone.name, polygon[0][0] + 5, polygon[0][1] + 20);
            }
        });
    }
    
    drawTracks() {
        this.tracks.forEach(track => {
            const bbox = track.bbox;
            if (!bbox || bbox.length < 4) return;
            
            // bbox is [x_center, y_center, width, height]
            const x1 = bbox[0] - bbox[2] / 2;
            const y1 = bbox[1] - bbox[3] / 2;
            const x2 = bbox[0] + bbox[2] / 2;
            const y2 = bbox[1] + bbox[3] / 2;
            
            // Draw bounding box (green)
            this.ctx.strokeStyle = '#00FF00';
            this.ctx.lineWidth = 2;
            this.ctx.strokeRect(x1, y1, x2 - x1, y2 - y1);
            
            // Draw label
            const label = `ID:${track.track_id} ${track.class} ${track.dwell_time?.toFixed(1) || 0}s`;
            this.ctx.fillStyle = '#00FF00';
            this.ctx.font = 'bold 14px Arial';
            this.ctx.fillText(label, x1, y1 - 5);
        });
    }
    
    draw() {
        // Clear canvas
        this.ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);
        
        // Draw zones first (background)
        this.drawZones();
        
        // Draw tracks on top
        this.drawTracks();
        
        // Continue animation loop
        this.animationId = requestAnimationFrame(() => this.draw());
    }
    
    start() {
        this.draw();
    }
    
    stop() {
        if (this.animationId) {
            cancelAnimationFrame(this.animationId);
        }
    }
}

// Export for use in HTML
if (typeof module !== 'undefined' && module.exports) {
    module.exports = ZoneOverlay;
}

