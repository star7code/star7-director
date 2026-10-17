__version__="0.2.7"
from .nodes import NODE_CLASS_MAPPINGS,NODE_DISPLAY_NAME_MAPPINGS
# Register only the private preview endpoint during normal plugin loading.
from .vendor.h3 import h3_live_preview as _private_preview
from . import routes
WEB_DIRECTORY='./web'
from pathlib import Path
from .run_diagnostics import install_fault_handler
install_fault_handler(Path(__file__).parent/'data')
