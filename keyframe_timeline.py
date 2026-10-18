"""Editable absolute keyframe times; validation at generation never rewrites drafts."""
import math

FRAME_PREFIX = '__star7_keyframe_'

def active_endpoints(shot):
    return {k:v for k,v in shot.get('keyframes',{}).items() if k!='first' or not shot.get('keyframe_motion')}


def frame_reference_id(point_id):
    return FRAME_PREFIX + point_id + '__'


def reference_cards(shot):
    if shot.get('input_mode') != 'keyframes':
        return []
    cards = []
    endpoints = active_endpoints(shot)
    entries = [('__star7_first_frame__', '首帧', endpoints.get('first'))]
    entries.extend((frame_reference_id(p['id']), '关键帧'+str(i+1), p) for i,p in enumerate(active_points(shot)))
    entries.append(('__star7_last_frame__', '尾帧', endpoints.get('last')))
    for aid,name,item in entries:
        if not item or not (item.get('source') or item.get('from_previous')):
            continue
        media = {'type':'image', 'source':item.get('source') or '__star7_previous_tail__'}
        if item.get('from_previous'):
            media['from_previous'] = True
        cards.append({'id':aid, 'kind':'keyframe', 'name':name, 'description':'', 'media':[media], 'timeline_reference':True})
    return cards


def validate_points(shot):
    points = shot.get('keyframe_points', [])
    if not isinstance(points, list):
        raise ValueError('关键帧必须是列表')
    ids = set()
    for point in points:
        if not isinstance(point, dict) or not isinstance(point.get('id'), str) or not point['id'] or point['id'] in ids or point['id'] in ('first', 'last'):
            raise ValueError('关键帧 ID 缺失或重复')
        ids.add(point['id'])
        seconds = point.get('time_seconds')
        if isinstance(seconds, bool) or not isinstance(seconds, (int, float)) or not math.isfinite(seconds) or seconds < 0:
            raise ValueError('关键帧时间必须是大于等于 0 的秒数')
        if 'source' in point and not isinstance(point['source'], str):
            raise ValueError('关键帧图片地址必须是文字')
    return points


def active_points(shot):
    if shot.get('input_mode') != 'keyframes':return []
    points=[{**p,'time_seconds':round_time(p['time_seconds'])} for p in shot.get('keyframe_points', [])]
    return sorted(points, key=lambda p: (p['time_seconds'], p['id']))


def round_time(seconds):
    return math.floor(seconds*10+0.5+1e-9)/10


def generation_errors(shot):
    if shot.get('input_mode') != 'keyframes':
        return []
    duration = shot.get('duration', 5)
    endpoints = active_endpoints(shot)
    frames = max(1, round(duration * 24))
    occupied = {index for key, index in (('first', 0), ('last', frames-1)) if endpoints.get(key)}
    if shot.get('keyframe_motion'):occupied.add(0)
    errors = []
    for point in active_points(shot):
        t = point['time_seconds']
        if t > duration:
            errors.append(f'关键帧 {t:g} 秒超出镜头时长 {duration:g} 秒')
        elif not point.get('source'):
            errors.append(f'关键帧 {t:g} 秒尚未设置图片')
        else:
            index = min(frames-1, round(t*24))
            if index in occupied:
                errors.append(f'关键帧 {t:g} 秒与其他关键帧处于同一帧，请调整时间')
            occupied.add(index)
    return errors


def require_valid(shot):
    errors = generation_errors(shot)
    if errors:
        raise ValueError((shot.get('name') or shot.get('id', ''))+'：'+errors[0])


def guide_frame(seconds, duration, native_frames):
    # Map the editable clip's timeline to the native 17k+5 timeline. In
    # particular a guide at duration seconds anchors the last valid frame.
    requested = max(1, round(duration*24))
    index = min(requested-1, math.floor(round_time(seconds)*24+0.5))
    return 0 if requested <= 1 else round(index*(native_frames-1)/(requested-1))
