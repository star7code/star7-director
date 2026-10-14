from .nodes import NODE_CLASS_MAPPINGS,NODE_DISPLAY_NAME_MAPPINGS
from .export_node import Star7DirectorVideoExport
from .save_video import Star7DirectorSaveVideo
from .stage import Star7DirectorStage,Star7DirectorLivePreview
NODE_CLASS_MAPPINGS['Star7DirectorLivePreview']=Star7DirectorLivePreview
NODE_DISPLAY_NAME_MAPPINGS['Star7DirectorLivePreview']='镜头实时预览绑定 - Star7'
NODE_CLASS_MAPPINGS['Star7DirectorVideoExport']=Star7DirectorVideoExport
NODE_DISPLAY_NAME_MAPPINGS['Star7DirectorVideoExport']='视频导出 - Star7'
NODE_CLASS_MAPPINGS['Star7DirectorSaveVideo']=Star7DirectorSaveVideo
NODE_DISPLAY_NAME_MAPPINGS['Star7DirectorSaveVideo']='保存镜头成品 - Star7'
NODE_CLASS_MAPPINGS['Star7DirectorStage']=Star7DirectorStage
NODE_DISPLAY_NAME_MAPPINGS['Star7DirectorStage']='镜头阶段通知 - Star7'
from . import routes
WEB_DIRECTORY='./web'
from pathlib import Path
from .run_diagnostics import install_fault_handler
install_fault_handler(Path(__file__).parent/'data')
