"""Each existing material owns a category slot, independent of display name."""
import re
LABELS={'character':'人物','scene':'场景','prop':'物品','voice':'音色','video':'视频','effect':'特效'}
def initialize(library):
    counters=library.setdefault('sequences',{})
    for kind,label in LABELS.items():
        cards=[a for a in library['assets'] if a['kind']==kind];used=set();pending=[]
        for a in cards:
            match=re.fullmatch(re.escape(label)+r'(\d+)',a['name']);number=a.get('sequence')
            if type(number) is not int or number<1:number=int(match[1]) if match else 0
            if number and number not in used:a['sequence']=number;used.add(number)
            else:pending.append(a)
        slot=1
        for a in pending:
            while slot in used:slot+=1
            a['sequence']=slot;used.add(slot);slot+=1
        counters[kind]=max(used,default=0)
    return library

def next_name(library,kind):
    initialize(library);n=1;used={value for a in library['assets'] for value in (a['name'],a.get('id',''))};slots={a['sequence'] for a in library['assets'] if a['kind']==kind}
    while n in slots or LABELS[kind]+str(n) in used:n+=1
    return LABELS[kind]+str(n),n

def retire_alias(library,name,exclude_id=None):
    mention=re.compile(r"@(?:\{([^}]+)\}|([\w-]+))")
    for asset in library['assets']:
        if asset.get('id')==exclude_id or name not in asset.get('aliases',[]):continue
        for card in library['assets']:
            if card.get('description'):card['description']=mention.sub(lambda m:'@{'+asset['id']+'}' if (m[1] or m[2])==name else m[0],card['description'])
        asset['aliases']=[a for a in asset['aliases'] if a!=name]
