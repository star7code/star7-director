"""Deterministic storyboard recognition; preview is non-mutating and all-or-nothing."""
import copy,json,math,re
from .core import validate,compile_plan,_compile_shot,MENTION
ALIASES={'duration':('duration','duration_sec','seconds','时长','秒数'),'prompt':('prompt','提示词','镜头描述'),'name':('name','名称','镜头名称'),'mode':('mode','continuity_mode','延续模式'),'first_frame':('first_frame','首帧'),'last_frame':('last_frame','尾帧')}
def unique_object(pairs):
    out={}
    for key,value in pairs:
        if key in out:raise ValueError('JSON字段重复：'+key)
        out[key]=value
    return out
def no_constant(value):raise ValueError('JSON不支持数值：'+value)
def decode(text):
    if not isinstance(text,str) or not text.strip():raise ValueError('请粘贴镜头文本')
    if len(text.encode('utf-8'))>1024*1024:raise ValueError('镜头文本超过1 MiB')
    text=text.lstrip('\ufeff').strip();warnings=[]
    fences=re.findall(r'```(?:json|JSON)?[ \t]*\r?\n(.*?)```',text,re.S)
    if len(fences)>1:raise ValueError('发现多个JSON代码块，请仅保留最终镜头列表')
    if fences:text=fences[0].strip()
    decoder=json.JSONDecoder(object_pairs_hook=unique_object,parse_constant=no_constant)
    start=next((i for i,c in enumerate(text) if c in '[{'),None)
    if start is None:raise ValueError('需要JSON镜头列表：{"shots":[{"duration":5,"prompt":"..."}]}')
    try:obj,end=decoder.raw_decode(text,start)
    except json.JSONDecodeError as error:raise ValueError(f'JSON格式错误，第{error.lineno}行第{error.colno}列：{error.msg}') from error
    rest=text[end:].strip()
    if rest and any(c in rest for c in '[{'):raise ValueError('JSON后还有其他结构，请只粘贴最终镜头列表')
    if start or rest:warnings.append('已识别JSON，格式外的说明文字不会进入提示词')
    if isinstance(obj,list):obj={'shots':obj}
    elif isinstance(obj,dict) and 'shots' not in obj and any(k in obj for k in ALIASES['prompt']):obj={'shots':[obj]}
    if not isinstance(obj,dict) or not isinstance(obj.get('shots'),list):raise ValueError('JSON需要包含shots数组')
    exported=obj if obj.get('schema_version')=='1.0' and 'assets' in obj and 'id' in obj else None
    if exported:validate(exported)
    elif set(obj)-{'shots','schema_version'}:raise ValueError('镜头列表顶层仅支持shots和可选schema_version')
    if obj.get('schema_version','1.0')!='1.0':raise ValueError('不支持的schema_version')
    if not 1<=len(obj['shots'])<=1000:raise ValueError('一次需要1–1000个镜头')
    if exported:
        warnings.append('已读取导出的分镜文件，保留镜头参数；素材引用按当前素材库检查')
        return [{'duration':s['duration'],'prompt':s['prompt'],'name':s.get('name',s['id']),'mode':'I' if s.get('continuity',{}).get('mode','independent')=='independent' else 'R','_exported':s} for s in obj['shots']],warnings
    if any(isinstance(s,dict) and '_exported' in s for s in obj['shots']):raise ValueError('不支持的镜头字段：_exported')
    return obj['shots'],warnings

def recognize(plan,text,mode='append',reserved_ids=()):
    validate(plan)
    if mode not in ('append','replace'):raise ValueError('请选择追加或替换镜头')
    incoming,warnings=decode(text);candidate=copy.deepcopy(plan);existing=candidate['shots'] if mode=='append' else []
    start=max(int(candidate.get('shot_sequence',0)),*[int(m[1]) for sid in [*(s['id'] for s in candidate['shots']),*reserved_ids] if (m:=re.match(r'shot_(\d+)',sid))],0)
    names={value:a['id'] for a in plan['assets'] for value in [a['id'],a['name'],*a.get('aliases',[])]};by_id={a['id']:a for a in plan['assets']}
    rows=[];shots=[];errors=[];exported_ids={};used_names={s.get('name') for s in existing};allowed={k for keys in ALIASES.values() for k in keys}
    for i,item in enumerate(incoming,1):
        sid='shot_'+str(start+i).zfill(3);row={'index':i,'id':sid,'name':sid,'valid':False};rows.append(row)
        try:
            if not isinstance(item,dict):raise ValueError('镜头必须是JSON对象')
            source=item.get('_exported');extra=set(item)-allowed-({'_exported'} if source else set())
            if extra:raise ValueError('不支持的字段：'+', '.join(sorted(extra)))
            values={}
            for key,aliases in ALIASES.items():
                supplied=[item[a] for a in aliases if a in item]
                if supplied and any(v!=supplied[0] for v in supplied):raise ValueError(key+'字段出现相互冲突的值')
                if supplied:values[key]=supplied[0]
            if 'duration' not in values or 'prompt' not in values:raise ValueError('每个镜头需要duration秒数和prompt提示词')
            duration=values['duration']
            if isinstance(duration,str):
                match=re.fullmatch(r'\s*(\d+(?:\.\d+)?)\s*(?:s|seconds?|秒)?\s*',duration,re.I)
                if not match:raise ValueError('duration必须是数字秒数')
                duration=float(match[1]);warnings.append(f'镜头{i}的时长字符串已转换为{duration:g}秒')
            if isinstance(duration,bool) or not isinstance(duration,(int,float)) or not math.isfinite(duration) or not .1<=duration<=60:raise ValueError('时长范围为0.1–60秒，可用小数')
            prompt=values['prompt'];name=values.get('name',sid)
            if not isinstance(prompt,str) or not prompt.strip() or len(prompt)>20000:raise ValueError('prompt需要1–20000字的提示词正文')
            if not isinstance(name,str) or not name.strip() or len(name)>200:raise ValueError('name需要1–200字的名称，或省略name')
            name=name.strip();row.update(name=name,duration=duration)
            if name in used_names:raise ValueError('镜头名称重复：'+name+'；可省略name自动命名')
            if re.search(r'<(?:script|div|span|img|html|p|br)\b|<(?:Picture|Audio|Video)\s*\d+>',prompt,re.I):raise ValueError('提示词不能包含HTML或手写模型素材标签，请使用@引用')
            prompt=prompt.strip().replace('＠','@')
            if len(re.findall(r'<d>',prompt,re.I))!=len(re.findall(r'</d>',prompt,re.I)):raise ValueError('对白<d>标签没有完整闭合')
            from .references import DIALOGUE,TAIL_REFERENCE_ID,is_tail_reference,mention_name
            matches=list(MENTION.finditer(prompt));spans=[m.span() for m in matches]+[m.span() for m in DIALOGUE.finditer(prompt)]
            if any(not any(a<=m.start()<b for a,b in spans) for m in re.finditer('@',prompt)):raise ValueError('存在不完整的@引用，请使用完整@{素材名称}')
            def canonical(match):
                token=mention_name(match)
                if is_tail_reference(token,names) or token in ('__star7_first_frame__','__star7_selected_frame__'):return match[0]
                if token not in names:raise ValueError('未知素材 @'+token+'，请使用素材大纲中的引用标记')
                return '@{'+names[token]+'}'
            prompt=MENTION.sub(canonical,prompt)
            previous=[*existing,*shots]
            code=values.get('mode','R' if previous else 'I')
            if not isinstance(code,str):raise ValueError('mode只能是I（独立）、R（运动引导＋重绘）或F（尾帧画面参考）')
            code=code.strip().upper()
            frame_modes={'S':'first','E':'last','SE':'both','FIRST_FRAME':'first','LAST_FRAME':'last','FIRST_LAST_FRAMES':'both'}
            if code not in ('I','R','F','INDEPENDENT','MOTION_REDRAW','TAIL_REFERENCE',*frame_modes):raise ValueError('mode支持I、R、F，以及S首帧、E尾帧、SE首尾帧')
            if any(k in values for k in ('first_frame','last_frame')) and code not in frame_modes:raise ValueError('首尾帧字段需要使用S、E或SE模式')
            continuity={'mode':'independent'}
            if code in ('R','MOTION_REDRAW','F','TAIL_REFERENCE'):
                if not previous:raise ValueError('第一个镜头没有前段可参考，请使用mode="I"')
                continuity={'mode':'tail_reference' if code in ('F','TAIL_REFERENCE') else 'motion_redraw','source_shot':previous[-1]['id']}
            shot={'id':sid,'name':name,'duration':duration,'prompt':prompt,'seed':666,'seed_control':'increment','continuity':continuity,'post':{'hd':False,'face':False}}
            if code in frame_modes:
                needed=('first_frame',) if frame_modes[code]=='first' else ('last_frame',) if frame_modes[code]=='last' else ('first_frame','last_frame')
                if any(k in values and k not in needed for k in ('first_frame','last_frame')):raise ValueError('上传帧字段与选择的首尾帧模式不一致')
                endpoints={}
                for key in needed:
                    value=values.get(key)
                    if not isinstance(value,str) or not value.strip():raise ValueError('此模式需要'+key+'，请填写当前图片素材名称或@{素材ID}')
                    token=value.strip();match=MENTION.search(token)
                    if match and match[0]==token:token=mention_name(match)
                    asset=by_id.get(names.get(token));images=[m for m in asset.get('media',[]) if m.get('type')=='image'] if asset else []
                    if not images:raise ValueError(key+'未找到当前素材库中的图片：'+value)
                    endpoints['first' if key=='first_frame' else 'last']=copy.deepcopy(images[0])
                shot.update(input_mode='keyframes',keyframes=endpoints)
            if source:
                for key in ('seed','seed_control','post','input_mode','keyframes'):
                    if key in source:shot[key]=copy.deepcopy(source[key])
                continuity=copy.deepcopy(source.get('continuity',{'mode':'independent'}))
                if continuity.get('source_shot'):continuity['source_shot']=exported_ids.get(continuity['source_shot'],continuity['source_shot'])
                shot['continuity']=continuity;exported_ids[source['id']]=sid
            probe={**candidate,'shots':[shot]};compiled=_compile_shot(probe,sid)
            virtual={TAIL_REFERENCE_ID,'__star7_first_frame__','__star7_selected_frame__'}
            unresolved=[m for m in MENTION.finditer(compiled['prompt']) if mention_name(m) not in virtual and shot.get('input_mode')!='keyframes']
            if unresolved or re.search(r'<(?:script|div|span|img|html|p|br)\b',compiled['prompt'],re.I):raise ValueError('素材描述展开后仍有未解析引用或HTML，请先修改素材描述')
            fields=('subject_definitions','summary','retention_analysis','detailed_description','overall_soundscape','non_diegetic_music') if any(compiled['media'].values()) else ('integrated_multimodal_description','overall_soundscape','non_diegetic_music')
            missing=[field for field in fields if not re.search(r'(?mi)^\s*'+field+r'\s*:',prompt)]
            if re.search(r'<Scene\s+\d+>',prompt,re.I):warnings.append(f'镜头{i}使用了Scene标签；H3场景应定义为<Subject N>')
            if missing:warnings.append(f'镜头{i}缺少H3标准字段：'+', '.join(missing)+'；建议让AI按新版素材大纲重写')
            row.update(valid=True,prompt=prompt,model_prompt=compiled['prompt'],continuity=continuity,input_mode=shot.get('input_mode','reference'),keyframes=shot.get('keyframes',{}),references=[{'id':aid,'name':by_id[aid]['name']} for aid in compiled['labels']],media_counts={kind:len(items)+(len(shot.get('keyframes',{})) if kind=='image' else 0)+(1 if kind=='image' and compiled.get('continuity_reference') else 0) for kind,items in compiled['media'].items()},**({'continuity_reference':compiled['continuity_reference']} if compiled.get('continuity_reference') else {}))
            shots.append(shot);used_names.add(name)
        except (ValueError,KeyError,TypeError) as error:
            row['error']=str(error);errors.append({'index':i,'message':str(error)})
    if len(existing)+len(incoming)>1000:errors.append({'index':None,'message':'项目最多1000个镜头'})
    candidate['shots']=[*existing,*shots];candidate['shot_sequence']=start+len(incoming);candidate.pop('runtime',None)
    if not errors:
        try:compile_plan(candidate)
        except (ValueError,KeyError,TypeError) as error:errors.append({'index':None,'message':'项目整体检查失败：'+str(error)})
    return {'valid':not errors,'rows':rows,'errors':errors,'warnings':list(dict.fromkeys(warnings)),'candidate':candidate if not errors else None,'count':len(incoming),'total_duration':sum(s['duration'] for s in shots),'mode':mode}
