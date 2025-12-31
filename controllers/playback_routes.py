"""
Playback REST API routes
"""

from flask import Blueprint, jsonify, request, send_file
from datetime import datetime
import logging
import io

logger = logging.getLogger(__name__)

# Blueprint for playback routes
playback_bp = Blueprint('playback', __name__, url_prefix='/api/playback')

# Global reference to recording engine (set by app.py)
_recording_engine = None


def set_recording_engine(recording_engine):
    """Set the recording engine instance (called from app.py)"""
    global _recording_engine
    _recording_engine = recording_engine


# Define segment route FIRST (more specific pattern)
@playback_bp.route('/segment/<camera_id>/<path:segment_path>', methods=['GET'])
def get_segment(camera_id, segment_path):
    """
    Get segment file content

    Args:
        camera_id: Camera identifier
        segment_path: Relative path to segment file

    Returns:
        MP4 segment file
    """
    if not _recording_engine:
        return jsonify({'error': 'Recording engine not initialized'}), 503

    try:
        # Get playback manager
        playback_manager = _recording_engine.playback_manager

        # Get segment file
        content = playback_manager.get_segment_file(camera_id, segment_path)

        if content is None:
            return jsonify({'error': 'Segment not found'}), 404

        # Return as MP4 file with custom headers
        # NOTE: We serve the raw fMP4 file, but HLS.js should use EXTINF values
        # from the M3U8 playlist, not the file duration metadata
        response = send_file(
            io.BytesIO(content),
            mimetype='video/mp4',
            as_attachment=False
        )
        # Add headers to help HLS.js handle the file correctly
        response.headers['Accept-Ranges'] = 'bytes'
        response.headers['Cache-Control'] = 'public, max-age=3600'
        return response

    except Exception as e:
        logger.error(f"Error getting segment {segment_path}: {e}")
        return jsonify({'error': str(e)}), 500


# Define playlist route SECOND (more specific than generic camera_id)
@playback_bp.route('/<camera_id>/playlist.m3u8', methods=['GET'])
def get_hls_playlist(camera_id):
    """
    Get HLS M3U8 playlist for a camera in time range

    Query Parameters:
        start_time (ISO 8601) - Start time
        end_time (ISO 8601) - End time

    Returns:
        M3U8 playlist content
    """
    if not _recording_engine:
        return jsonify({'error': 'Recording engine not initialized'}), 503

    try:
        # Get query parameters
        start_time_str = request.args.get('start_time')
        end_time_str = request.args.get('end_time')

        if not start_time_str or not end_time_str:
            return jsonify({'error': 'start_time and end_time are required'}), 400

        try:
            start_time = datetime.fromisoformat(start_time_str)
            end_time = datetime.fromisoformat(end_time_str)
        except ValueError:
            return jsonify({'error': 'Invalid timestamp format'}), 400

        # Get playback manager
        playback_manager = _recording_engine.playback_manager

        # Get segments
        segments = playback_manager.get_segments_for_playback(camera_id, start_time, end_time)

        if not segments:
            return jsonify({'error': 'No segments found'}), 404

        # Generate playlist
        playlist = playback_manager.generate_hls_playlist(camera_id, segments)

        # Return as M3U8 file
        return playlist, 200, {'Content-Type': 'application/vnd.apple.mpegurl'}

    except Exception as e:
        logger.error(f"Error generating HLS playlist for {camera_id}: {e}")
        return jsonify({'error': str(e)}), 500


# Define export route THIRD (more specific than generic camera_id)
@playback_bp.route('/<camera_id>/export', methods=['POST'])
def export_clip(camera_id):
    """
    Export video clip for time range

    Request Body:
        {
            "start_time": "2025-11-11T12:00:00",
            "end_time": "2025-11-11T12:05:00",
            "format": "mp4"
        }

    Returns:
        MP4 file download
    """
    if not _recording_engine:
        return jsonify({'error': 'Recording engine not initialized'}), 503

    try:
        data = request.get_json()

        if not data:
            return jsonify({'error': 'Request body required'}), 400

        start_time_str = data.get('start_time')
        end_time_str = data.get('end_time')

        if not start_time_str or not end_time_str:
            return jsonify({'error': 'start_time and end_time are required'}), 400

        try:
            start_time = datetime.fromisoformat(start_time_str)
            end_time = datetime.fromisoformat(end_time_str)
        except ValueError:
            return jsonify({'error': 'Invalid timestamp format'}), 400

        # Get playback manager
        playback_manager = _recording_engine.playback_manager

        # Get segments
        segments = playback_manager.get_segments_for_playback(camera_id, start_time, end_time)

        if not segments:
            return jsonify({'error': 'No segments found for time range'}), 404

        # TODO: Implement actual clip export (concatenate segments)
        # For now, return info about what would be exported
        total_size = sum(s.get('file_size', 0) for s in segments)

        return jsonify({
            'camera_id': camera_id,
            'start_time': start_time.isoformat(),
            'end_time': end_time.isoformat(),
            'segment_count': len(segments),
            'total_size_bytes': total_size,
            'status': 'Export functionality coming soon'
        }), 200

    except Exception as e:
        logger.error(f"Error exporting clip for {camera_id}: {e}")
        return jsonify({'error': str(e)}), 500


# Define generic playback info route LAST (least specific pattern)
@playback_bp.route('/<camera_id>', methods=['GET'])
def get_playback_info(camera_id):
    """
    Get playback information for a camera in time range

    Query Parameters:
        start_time (ISO 8601) - Start time for playback
        end_time (ISO 8601) - End time for playback

    Returns:
        {
            "camera_id": "wisenet_front",
            "start_time": "2025-11-11T12:00:00",
            "end_time": "2025-11-11T13:00:00",
            "segment_count": 1200,
            "total_duration_ms": 3600000,
            "total_size_bytes": 524288000,
            "segments": [...],
            "playlist_url": "/api/playback/wisenet_front/playlist.m3u8?..."
        }
    """
    if not _recording_engine:
        return jsonify({'error': 'Recording engine not initialized'}), 503

    try:
        # Get query parameters
        start_time_str = request.args.get('start_time')
        end_time_str = request.args.get('end_time')

        # Parse timestamps
        if not start_time_str or not end_time_str:
            return jsonify({'error': 'start_time and end_time are required'}), 400

        try:
            start_time = datetime.fromisoformat(start_time_str)
            end_time = datetime.fromisoformat(end_time_str)
        except ValueError:
            return jsonify({'error': 'Invalid timestamp format. Use ISO 8601'}), 400

        # Get playback manager
        playback_manager = _recording_engine.playback_manager

        # Get playback info
        info = playback_manager.get_playback_info(camera_id, start_time, end_time)

        if 'error' in info:
            return jsonify(info), 404

        return jsonify(info), 200

    except Exception as e:
        logger.error(f"Error getting playback info for {camera_id}: {e}")
        return jsonify({'error': str(e)}), 500

