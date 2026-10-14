"""Material references exclude literal dialogue/lyrics inside H3 <d> blocks."""
import re
PATTERN=re.compile(r"@(?:\{([^}]+)\}|([\w-]+))")
DIALOGUE=re.compile(r"<d>.*?</d>",re.I|re.S)
TAIL_REFERENCE_ID='__star7_tail_frame__'
SELECTED_REFERENCE_ID='__star7_selected_frame__'
def is_tail_reference(token,material_names=()):
    return token==TAIL_REFERENCE_ID
def mention_name(match):
    # Only the exact braced spelling activates the virtual tail reference.
    # The old internal ID remains readable for already saved workflows.
    return TAIL_REFERENCE_ID if match[1] in ('尾帧','尾帧参考') else '__star7_first_frame__' if match[1]=='首帧' else SELECTED_REFERENCE_ID if match[1]=='参考帧' else match[1] or match[2]
class ReferencePattern:
    def finditer(self,text):
        spans=[m.span() for m in DIALOGUE.finditer(text)]
        return (m for m in PATTERN.finditer(text) if not any(a<=m.start()<b for a,b in spans))
    def sub(self,replace,text):
        out=[];end=0
        for m in self.finditer(text):out.extend((text[end:m.start()],replace(m)));end=m.end()
        out.append(text[end:]);return ''.join(out)
    def search(self,text):return next(self.finditer(text),None)
MENTION=ReferencePattern()
