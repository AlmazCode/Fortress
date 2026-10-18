"""Local bulk human annotation of the existing Fortress source frames.

Run: python -B -m tools.label_review --root <training-ready> --data <private-dir>
No model predictions are prefilled. Only explicit user answers become reviewed
labels; unknown answers stay masked. Original datasets and model fits are read-only.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import sqlite3
import subprocess
import tempfile
import threading

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from pydantic import BaseModel, ConfigDict, Field

VERSION = 'fortress-human-review-v1'
UI = Path(__file__).with_name('label_review_ui')
QUESTIONS = [
    {'id':'storage_open','title':'Сейф: состояние дверцы','help':'Открыта — виден зазор или внутренняя часть. Закрыта — дверца прилегает. Закрытая дверца не доказывает запирание. Если объект или дверца не видны — «Не видно».',
     'choices':[['open','Открыта'],['closed','Закрыта'],['unknown','Не видно / не уверен']]},
    {'id':'bag_position','title':'Сумка: где находится','help':'«На столе» — сумка опирается на стол. «В руках» — сотрудник держит её над поверхностью. Если сумку не видно, её отсутствие не утверждаем.',
     'choices':[['on_desk','На столе'],['in_hands','В руках'],['elsewhere','В другом месте'],['unknown','Не видно / не уверен']]},
    {'id':'bag_interaction','title':'Действие: работа с сумкой','help':'Да — сотрудник берёт, перемещает, открывает или закрывает сумку. Простое наличие сумки не считается действием. Для движения посмотрите контекст.',
     'choices':[['yes','Да, работает с сумкой'],['no','Нет действия'],['unknown','Не видно / не уверен']]},
    {'id':'storage_interaction','title':'Действие: работа с сейфом','help':'Да — контакт с ручкой, дверцей или внутренней частью сейфа. Содержимое и запирание не угадываем.',
     'choices':[['yes','Да, работает с сейфом'],['no','Нет действия'],['unknown','Не видно / не уверен']]},
    {'id':'laptop_screen_lit','title':'Экран ноутбука','help':'Светится / тёмный — только когда видна поверхность дисплея. По светящемуся экрану нельзя установить блокировку ОС.',
     'choices':[['lit','Светится'],['dark','Тёмный'],['unknown','Не видно / не уверен']]},
    {'id':'computer_interaction','title':'Действие: работа с компьютером','help':'Руки на клавиатуре, тачпаде или движение крышки. Сам по себе светящийся экран — не действие.',
     'choices':[['yes','Да, работает'],['no','Нет действия'],['unknown','Не видно / не уверен']]},
    {'id':'flat_item_handling','title':'Действие: купюра, карточка, бумага','help':'Видна работа с плоским предметом. Не нужно угадывать номинал, подлинность, личность или факт подмены.',
     'choices':[['yes','Да, работает с предметом'],['no','Нет действия'],['unknown','Не видно / не уверен']]},
    {'id':'counter_interaction','title':'Действие: настольное устройство','help':'Рука подаёт или забирает предмет, касается устройства проверки/пересчёта. Наличие устройства само по себе не является действием.',
     'choices':[['yes','Да, работает с устройством'],['no','Нет действия'],['unknown','Не видно / не уверен']]},
    {'id':'operator_at_station','title':'Сотрудник у рабочего места','help':'Сотрудник физически находится у стола или сейфа. Людей в отражении не учитываем.',
     'choices':[['yes','Присутствует'],['no','Отсутствует'],['unknown','Не видно / не уверен']]},
    {'id':'person_at_counter','title':'Клиент у стойки','help':'Другой человек физически находится рядом со стойкой. Отражения и ожидающие за стеклом не считаются.',
     'choices':[['yes','Есть человек'],['no','Нет человека'],['unknown','Не видно / не уверен']]},
    {'id':'glass_door_open','title':'Дверь прохода','help':'Оценивайте физическое состояние двери прохода. Право доступа и полномочия не угадываем.',
     'choices':[['open','Открыта'],['closed','Закрыта'],['unknown','Не видно / не уверен']]},
    {'id':'writing','title':'Действие: запись на бумаге','help':'Видно движение ручки по бумаге или журналу. Для оценки движения используйте контекст.',
     'choices':[['yes','Да, пишет'],['no','Нет действия'],['unknown','Не видно / не уверен']]},
    {'id':'safe_object_confirmed','title':'Объект: это сейф?','help':'Подтвердите объект: серый металлический шкаф рядом с рабочим столом — это сейф? Если сам объект не виден, выбирайте «Не видно». Это отдельный признак, а не состояние дверцы.',
     'choices':[['yes','Да, это сейф'],['no','Это другой объект'],['unknown','Не видно / не уверен']]},
]
CHOICES = {q['id']:{c[0] for c in q['choices']} for q in QUESTIONS}


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def digest(value):
    return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def file_hash(path):
    with Path(path).open('rb') as source:return hashlib.file_digest(source,'sha256').hexdigest()


def atomic_json(path,value):
    path=Path(path);fd,name=tempfile.mkstemp(dir=path.parent,prefix='.review-',suffix='.json')
    try:
        with os.fdopen(fd,'w',encoding='utf-8') as out:
            json.dump(value,out,ensure_ascii=False,indent=2,allow_nan=False);out.write('\n');out.flush();os.fsync(out.fileno())
        os.replace(name,path)
    finally:Path(name).unlink(missing_ok=True)


def prepare(root,data):
    root,data=Path(root).resolve(strict=True),Path(data).resolve()
    if any((p/'.git').exists() for p in [data,*data.parents]):raise ValueError('Answers and media must be outside Git')
    plan=read_json(root/'temporal-operations-stage-v1c/protocol.json')
    marker=read_json(root/'spatial-inputs-v2/inputs.json');entries={r['video_id']:r for r in marker['entries']}
    source=Path(read_json(root/'prepared/readiness.json')['source_root']).resolve(strict=True)
    development=plan['development_ids']
    if set(development)&set(plan['reserved_ids']):raise ValueError('Reserved source in review set')
    priority=['video_008','video_014','video_015','video_016','video_017','video_005','video_019','video_025','video_035','video_039']
    order=[v for v in priority if v in development]+[v for v in development if v not in priority]
    videos=[];frames=[]
    for video in order:
        path=root/'prepared/indices'/(video+'.json');index=read_json(path);entry=entries[video]
        if index['source_sha256']!=entry['source_sha256']:raise ValueError('Review source identity changed')
        actual=(source/index['path']).resolve(strict=True)
        if source not in actual.parents:raise ValueError('Source escaped dataset root')
        timing={r['source_pts']:r['timestamp_sec'] for r in index['frames']}
        videos.append({'id':video,'path':str(actual),'index':str(path),'index_sha256':file_hash(path),
                       'source_sha256':index['source_sha256'],'time_base':index['time_base'],
                       'origin_pts':index['origin_pts'],'duration_sec':index['duration_sec'],'group_id':index['group_id']})
        for point in entry['source_pts']:
            frames.append({'id':video+'-'+str(point),'video_id':video,'source_pts':point,'timestamp_sec':timing[point]})
    manifest={'version':VERSION,'source_root':str(source),'videos':videos,'frames':frames,
              'reserved_ids':plan['reserved_ids'],'questions':QUESTIONS,'sampling':'existing exact source PTS at 2fps',
              'independent_test':False,'unseen_intervals_are_unknown':True}
    manifest['sha256']=digest(manifest);data.mkdir(parents=True,exist_ok=True);target=data/'manifest.json'
    if target.exists():
        if read_json(target)!=manifest:raise ValueError('Existing review dataset differs; choose a new data directory')
    else:atomic_json(target,manifest)
    return manifest


class ReviewStore:
    def __init__(self,data,manifest):
        self.data=Path(data);self.manifest=manifest;self.frames={f['id']:f for f in manifest['frames']};self.path=self.data/'review.sqlite3'
        with self.connect() as db:
            db.executescript('''PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS metadata (id INTEGER PRIMARY KEY CHECK(id=1), manifest TEXT NOT NULL, revision INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS answers (frame TEXT NOT NULL, question TEXT NOT NULL, answer TEXT NOT NULL, PRIMARY KEY(frame,question));
                CREATE TABLE IF NOT EXISTS history (revision INTEGER PRIMARY KEY, kind TEXT NOT NULL, payload TEXT NOT NULL, undone INTEGER NOT NULL DEFAULT 0, created TEXT NOT NULL);''')
            row=db.execute('SELECT manifest FROM metadata WHERE id=1').fetchone()
            if row and row[0]!=manifest['sha256']:raise ValueError('Answers belong to another dataset')
            db.execute('INSERT OR IGNORE INTO metadata VALUES(1,?,0)',(manifest['sha256'],))

    def connect(self):
        db=sqlite3.connect(self.path,timeout=10);db.execute('PRAGMA synchronous=FULL');return db

    def snapshot(self):
        with self.connect() as db:
            db.execute('BEGIN');revision=db.execute('SELECT revision FROM metadata WHERE id=1').fetchone()[0]
            answers={}
            for frame,question,answer in db.execute('SELECT frame,question,answer FROM answers'):
                answers.setdefault(frame,{})[question]=json.loads(answer)
            return {'revision':revision,'answers':answers}

    def save(self,changes,expected):
        # Validate the complete batch before opening a write transaction.
        if not 1<=len(changes)<=200:raise ValueError('Batch size must be 1..200')
        unique={}
        for change in changes:
            f,q,v=change['frame_id'],change['question'],change['value']
            if f not in self.frames or q not in CHOICES or v not in CHOICES[q]:raise ValueError('Unknown frame/question/answer')
            unique[(f,q)]=v
        now=datetime.now(timezone.utc).isoformat();payload=[]
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE');revision=db.execute('SELECT revision FROM metadata WHERE id=1').fetchone()[0]
            if expected!=revision:raise RuntimeError('revision_conflict')
            for (f,q),value in unique.items():
                old=db.execute('SELECT answer FROM answers WHERE frame=? AND question=?',(f,q)).fetchone()
                if old and json.loads(old[0])['value']==value:continue
                answer={'value':value,'reviewed_at':now,'reviewer':'local_human','human_approved':True,'known':value!='unknown'}
                payload.append({'frame_id':f,'question':q,'before':json.loads(old[0]) if old else None,'after':answer})
                db.execute('INSERT OR REPLACE INTO answers VALUES(?,?,?)',(f,q,json.dumps(answer)))
            if payload:
                revision+=1;db.execute('UPDATE metadata SET revision=? WHERE id=1',(revision,))
                db.execute('INSERT INTO history(revision,kind,payload,created) VALUES(?,?,?,?)',(revision,'answer',json.dumps(payload),now))
        return self.snapshot()

    def undo(self,expected):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE');revision=db.execute('SELECT revision FROM metadata WHERE id=1').fetchone()[0]
            if revision!=expected:raise RuntimeError('revision_conflict')
            row=db.execute("SELECT revision,payload FROM history WHERE kind='answer' AND undone=0 ORDER BY revision DESC LIMIT 1").fetchone()
            if row:
                for change in json.loads(row[1]):
                    f,q=change['frame_id'],change['question']
                    if change['before'] is None:db.execute('DELETE FROM answers WHERE frame=? AND question=?',(f,q))
                    else:db.execute('INSERT OR REPLACE INTO answers VALUES(?,?,?)',(f,q,json.dumps(change['before'])))
                db.execute('UPDATE history SET undone=1 WHERE revision=?',(row[0],));revision+=1
                db.execute('UPDATE metadata SET revision=? WHERE id=1',(revision,))
                db.execute('INSERT INTO history(revision,kind,payload,created) VALUES(?,?,?,?)',
                           (revision,'undo',json.dumps({'undo_revision':row[0]}),datetime.now(timezone.utc).isoformat()))
        return self.snapshot()

    def export(self):
        snapshot=self.snapshot();videos={v['id']:v for v in self.manifest['videos']};records=[]
        for frame_id,answers in snapshot['answers'].items():
            frame=self.frames[frame_id];video=videos[frame['video_id']]
            for question,answer in answers.items():
                target=question;value=answer['value'];numeric=-1
                if value in ('yes','open','lit'):numeric=1
                elif value in ('no','closed','dark'):numeric=0
                if question=='bag_position':
                    target='bag_on_desk';numeric={'on_desk':1,'in_hands':0,'elsewhere':0,'unknown':-1}[value]
                records.append({**frame,'source_sha256':video['source_sha256'],'group_id':video['group_id'],
                                'time_base':video['time_base'],'origin_pts':video['origin_pts'],'question':question,
                                **answer,'training_class':target,'training_value':numeric,'known':numeric>=0})
        result={'version':VERSION,'manifest_sha256':self.manifest['sha256'],'revision':snapshot['revision'],
                'records':records,'human_approved_records':len(records),'independent_test':False,
                'no_interval_extrapolation':True,'training_started':False,'original_labels_changed':False}
        directory=self.data/'exports';directory.mkdir(exist_ok=True);path=directory/f"human-review-r{snapshot['revision']:06}.json"
        if path.exists():
            if read_json(path)!=result:raise ValueError('Immutable export changed')
        else:atomic_json(path,result)
        return path


class SourceMedia:
    def __init__(self,data,manifest):
        self.data=Path(data);self.manifest=manifest;self.frames={f['id']:f for f in manifest['frames']};self.videos={v['id']:v for v in manifest['videos']}
        self.locks={v:threading.Lock() for v in self.videos};self.ready=set();self.clip_lock=threading.Lock()

    def images(self,video):
        with self.locks[video]:
            if video in self.ready:return
            row=self.videos[video];directory=self.data/'images'/video;receipt=directory/'receipt.json'
            if receipt.exists():
                cached=read_json(receipt)
                if cached['source_sha256']==row['source_sha256'] and all((directory/p).is_file() and file_hash(directory/p)==sha for p,sha in cached['images'].items()):
                    self.ready.add(video);return
                raise ValueError('Source image cache changed')
            if file_hash(row['index'])!=row['index_sha256']:raise ValueError('Source index changed')
            from ml.data.pts_index import iter_indexed_frames
            from ml.data.extract_frames import display_transform,transformed_image
            index=read_json(row['index']);selected={f['source_pts']:f['id'] for f in self.manifest['frames'] if f['video_id']==video}
            directory.mkdir(parents=True,exist_ok=True);images={}
            for timing,frame in iter_indexed_frames(Path(self.manifest['source_root']),index):
                point=timing['source_pts']
                if point in selected:
                    im=transformed_image(frame.to_image(),display_transform(index));im.thumbnail((1200,1200))
                    path=directory/(selected[point]+'.jpg');im.save(path,quality=90);images[path.name]=file_hash(path)
            if len(images)!=len(selected):raise ValueError('Source frames missing')
            atomic_json(receipt,{'source_sha256':row['source_sha256'],'images':images});self.ready.add(video)

    def frame(self,frame_id):
        if frame_id not in self.frames:raise KeyError(frame_id)
        self.images(self.frames[frame_id]['video_id']);return self.data/'images'/self.frames[frame_id]['video_id']/(frame_id+'.jpg')

    def context(self,frame_id):
        frame=self.frames[frame_id];row=self.videos[frame['video_id']];start=max(0.,frame['timestamp_sec']-2.5)
        with self.clip_lock:
            directory=self.data/'contexts';directory.mkdir(exist_ok=True);path=directory/(frame_id+'.mp4')
            if not path.exists():
                if file_hash(row['path'])!=row['source_sha256']:raise ValueError('Original source changed')
                executable=shutil.which('ffmpeg')
                if not executable:
                    config=Path(os.environ.get('LOCALAPPDATA',str(Path.home())))/'Fortress/local-config.json'
                    executable=str(Path(read_json(config)['ffmpeg_dir'])/'ffmpeg.exe')
                temporary=path.with_suffix('.partial.mp4')
                try:
                    subprocess.run([executable,'-v','error','-nostdin','-threads','2','-ss',str(start),'-i',row['path'],
                                    '-t','5','-map','0:v:0','-an','-sn','-dn','-map_metadata','-1','-vf','setpts=PTS-STARTPTS',
                                    '-c:v','libx264','-preset','veryfast','-crf','24','-threads','2','-pix_fmt','yuv420p',
                                    '-movflags','+faststart','-y',str(temporary)],check=True,timeout=35,
                                   stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
                    os.replace(temporary,path)
                finally:temporary.unlink(missing_ok=True)
            return path,start


class Change(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True)
    frame_id:str
    question:str
    value:str


class Batch(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True)
    revision:int=Field(ge=0)
    changes:list[Change]=Field(min_length=1,max_length=200)


class Undo(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True)
    revision:int=Field(ge=0)


def create_app(data,manifest,*,media=None):
    store=ReviewStore(data,manifest);media=media or SourceMedia(data,manifest);session=secrets.token_urlsafe(32)
    app=FastAPI(docs_url=None,redoc_url=None,openapi_url=None)
    app.state.store=store
    @app.middleware('http')
    async def local_only(request,call_next):
        if request.url.hostname not in ('127.0.0.1','localhost','testserver'):
            return JSONResponse({'detail':'Local host required'},status_code=403)
        if request.url.path.startswith('/api/'):
            if not secrets.compare_digest(request.cookies.get('fortress_review',''),session):
                return JSONResponse({'detail':'Open the review page first'},status_code=403)
            if request.method!='GET' and request.headers.get('origin')!=str(request.base_url).rstrip('/'):
                return JSONResponse({'detail':'Same-origin JSON request required'},status_code=403)
        response=await call_next(request);response.headers['Cache-Control']='no-store';response.headers['X-Content-Type-Options']='nosniff'
        response.headers['Content-Security-Policy']="default-src 'self'; img-src 'self'; media-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
        return response
    @app.get('/')
    def index():
        response=FileResponse(UI/'index.html');response.set_cookie('fortress_review',session,httponly=True,samesite='strict');return response
    @app.get('/healthz')
    def health():return {'app':VERSION,'manifest_sha256':manifest['sha256']}
    @app.get('/{asset}')
    def asset(asset:str):
        if asset not in ('app.js','style.css'):raise HTTPException(404)
        return FileResponse(UI/asset)
    @app.get('/api/session')
    def state():
        public_videos=[{k:v[k] for k in ('id','duration_sec','group_id')} for v in manifest['videos']]
        return {'app':VERSION,'manifest_sha256':manifest['sha256'],'questions':QUESTIONS,
                'videos':public_videos,'frames':manifest['frames'],**store.snapshot()}
    def operation(function,*args):
        try:return function(*args)
        except RuntimeError as error:raise HTTPException(409,'Ответы изменены в другой вкладке. Обновите страницу.') from error
        except (ValueError,KeyError) as error:raise HTTPException(400,str(error)) from error
    @app.post('/api/answers')
    def answers(batch:Batch):return operation(store.save,[c.model_dump() for c in batch.changes],batch.revision)
    @app.post('/api/undo')
    def undo(batch:Undo):return operation(store.undo,batch.revision)
    @app.post('/api/shutdown')
    def shutdown():
        callback=getattr(app.state,'shutdown',None)
        if callback is None:raise HTTPException(503,'Shutdown unavailable')
        callback();return {'status':'stopping'}
    @app.get('/api/export')
    def export():return FileResponse(store.export(),media_type='application/json',filename='fortress-human-review.json')
    @app.get('/api/frame/{frame_id}')
    def image(frame_id:str):
        try:return FileResponse(media.frame(frame_id),media_type='image/jpeg')
        except KeyError:raise HTTPException(404,'Unknown source frame') from None
    @app.get('/api/context/{frame_id}')
    def context(frame_id:str):
        try:path,start=media.context(frame_id)
        except KeyError:raise HTTPException(404,'Unknown source frame') from None
        return FileResponse(path,media_type='video/mp4',headers={'X-Source-Start-Sec':str(start)})
    return app


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=Path.home()/'FortressArtifacts/training-ready')
    parser.add_argument('--data',type=Path,default=Path(os.environ.get('LOCALAPPDATA',str(Path.home())))/'Fortress/human-review-v1')
    parser.add_argument('--port',type=int,default=8766);args=parser.parse_args()
    manifest=prepare(args.root,args.data)
    import uvicorn
    print(f'Fortress annotation: http://127.0.0.1:{args.port}/; {len(manifest["frames"])} frames',flush=True)
    app=create_app(args.data,manifest)
    server=uvicorn.Server(uvicorn.Config(app,host='127.0.0.1',port=args.port,access_log=False,log_level='warning'))
    app.state.shutdown=lambda:setattr(server,'should_exit',True)
    server.run()


if __name__=='__main__':main()
