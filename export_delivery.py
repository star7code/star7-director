"""Actions restricted to indexed export files; no client-supplied filesystem paths."""
import os,shutil,uuid,zipfile
from pathlib import Path
from .core import identifier
from .storage import Storage

def export_files(data_root,output_root,project,filename):
    project=identifier(project)
    if not isinstance(filename,str) or Path(filename).name!=filename:raise ValueError('导出文件名无效')
    root=Path(output_root).resolve();store=Storage(data_root);record=store.film_path(project,filename)
    if not record:raise ValueError('导出记录不存在')
    anchor=Path(record).resolve()
    def valid(p):return p.is_relative_to(root) and p.is_file() and p.suffix.lower() in ('.mp4','.webm')
    if not valid(anchor):raise ValueError('导出视频不可用')
    grouped=any(marker in anchor.parent.name for marker in ('-分段导出-','-合并导出-'))
    paths=[anchor]
    if grouped:
        with store.db(project,create=False) as db:rows=db.execute('SELECT path FROM films WHERE project=?',(project,)).fetchall()
        paths=sorted({Path(row[0]).resolve() for row in rows if Path(row[0]).resolve().parent==anchor.parent},key=lambda p:p.name)
        if not paths or any(not valid(p) for p in paths):raise ValueError('部分导出文件已移动或删除，请重新导出')
    return anchor,paths,grouped

def downloads_directory():
    if os.name!='nt':return Path.home()/'Downloads'
    import ctypes
    from ctypes import wintypes
    # FOLDERID_Downloads honors the user's redirected Downloads folder.
    guid=(ctypes.c_ubyte*16).from_buffer_copy(uuid.UUID('374DE290-123F-4565-9164-39C4925E467B').bytes_le)
    pointer=ctypes.c_wchar_p();function=ctypes.windll.shell32.SHGetKnownFolderPath
    function.argtypes=[ctypes.c_void_p,wintypes.DWORD,wintypes.HANDLE,ctypes.POINTER(ctypes.c_wchar_p)];function.restype=ctypes.c_long
    if function(ctypes.byref(guid),0,None,ctypes.byref(pointer))<0:raise ValueError('无法定位系统下载目录，请使用 ZIP 下载')
    try:return Path(pointer.value)
    finally:ctypes.windll.ole32.CoTaskMemFree(ctypes.cast(pointer,ctypes.c_void_p))

def copy_to_downloads(anchor,paths,grouped,downloads=None):
    base=Path(downloads if downloads is not None else downloads_directory()).resolve();base.mkdir(parents=True,exist_ok=True)
    if not grouped:raise ValueError('单镜头请使用视频下载按钮')
    name=anchor.parent.name;number=1
    while True:
        target=base/(name+('' if number==1 else '-'+str(number)))
        if not target.resolve().is_relative_to(base):raise ValueError('下载目录路径无效')
        try:target.mkdir();break
        except FileExistsError:number+=1
    try:
        for source in paths:shutil.copy2(source,target/source.name)
    except BaseException:
        if target.resolve().is_relative_to(base):shutil.rmtree(target)
        raise
    return target

def open_directory(anchor):
    if os.name!='nt':raise ValueError('当前服务器不支持快捷打开目录，请使用 ZIP 下载')
    os.startfile(str(anchor.parent))

def open_video(anchor):
    if os.name!='nt':raise ValueError('当前服务器不支持快捷打开视频，请使用页面预览或下载')
    os.startfile(str(anchor))

def build_archive(target,anchor,paths):
    with zipfile.ZipFile(target,'w',compression=zipfile.ZIP_STORED,allowZip64=True) as archive:
        for path in paths:archive.write(path,arcname=anchor.parent.name+'/'+path.name)

def choose_native_directory():
    """Interactive Windows dialog. Paths never come from HTTP request data."""
    if os.name!='nt':raise ValueError('此浏览器不支持目录选择，请使用 Chrome／Edge')
    import subprocess,json,base64,threading
    script=(Path(__file__).with_name('native-folder-dialog.ps1')).read_text(encoding='utf-8')
    if not _picker_lock.acquire(blocking=False):raise ValueError('目录选择窗口已打开，请先完成或取消选择')
    try:
        encoded=base64.b64encode(script.encode('utf-16-le')).decode('ascii')
        result=subprocess.run(['powershell.exe','-NoProfile','-STA','-EncodedCommand',encoded],capture_output=True,creationflags=subprocess.CREATE_NO_WINDOW)
        if result.returncode:raise ValueError('无法打开 Windows 目录选择窗口')
        selected=json.loads(result.stdout.decode('utf-8-sig').strip())
        if selected is None:return None
        directory=Path(selected).resolve()
        if not directory.is_dir():raise ValueError('所选目录不可用')
        return directory
    finally:_picker_lock.release()

import threading
_picker_lock=threading.Lock()

def save_native(data_root,output_root,body):
    from .export_settings import settings,extension,needs_encoding,export_clip
    project=identifier(body.get('project_id'));single=body.get('scope')=='one'
    if single:
        shot=identifier(body.get('shot_id'));record=Storage(data_root).latest_output(project,shot)
        if not record:raise ValueError('当前镜头尚未生成视频')
        source=Path(record['path']).resolve();root=Path(output_root).resolve()
        if not source.is_relative_to(root) or not source.is_file():raise ValueError('当前镜头成品不可用')
        plan={'id':project,'title':body.get('title',project),'shots':[body.get('shot',{'id':shot})],'export_settings':body.get('export_settings',{})};settings(plan)
        name=source.stem+'.'+extension(plan)
    else:
        anchor,paths,grouped=export_files(data_root,output_root,project,body.get('filename'))
        if not grouped:raise ValueError('此导出不是分段或合并文件夹')
        name=anchor.parent.name+'.zip'
    directory=choose_native_directory()
    if directory is None:return {'cancelled':True,'message':'已取消选择目录'}
    if not single and not body.get('zip'):
        target=copy_to_downloads(anchor,paths,True,directory)
        return {'message':str(len(paths))+' 个视频已保存到：'+str(target)}
    number=1
    while True:
        target=directory/(Path(name).stem+('' if number==1 else '-'+str(number))+Path(name).suffix)
        try:
            with target.open('xb'):pass
            break
        except FileExistsError:number+=1
    try:
        if not single:build_archive(target,anchor,paths)
        elif needs_encoding(plan):export_clip(source,target,plan)
        else:shutil.copy2(source,target)
    except BaseException:
        if target.resolve().parent==directory:target.unlink(missing_ok=True)
        raise
    return {'message':'已保存到：'+str(target)}
