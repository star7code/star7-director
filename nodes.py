"""Only the workstation and material library are public ComfyUI nodes."""
from pathlib import Path
DATA=Path(__file__).resolve().parent/'data'
from .desk import Star7DirectorDesk,Star7DirectorLibrary
NODE_CLASS_MAPPINGS={'Star7DirectorDesk':Star7DirectorDesk,'Star7DirectorLibrary':Star7DirectorLibrary}
NODE_DISPLAY_NAME_MAPPINGS={'Star7DirectorDesk':'导演台工作站 - Star7','Star7DirectorLibrary':'项目素材库 - Star7'}
