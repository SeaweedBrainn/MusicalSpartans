"""Strict note-level format V2. Preserve rows; estimate overall accuracy only from the clarified zero-baseline deltas."""
import math
import re

HEADER = ['note_index','time_ms','lane','judgement','accuracy_delta','latency_ms','nps','bpm','combo','std_ms']


def parse(records):
    from game_runs import integer, number
    names = ['game_id','song_id','chart_id','bpm','format_version']
    if len(records) < 6 or any(len(records[i]) != 2 or records[i][0] != name for i,name in enumerate(names)):
        raise ValueError('V2 metadata must be game_id, song_id, chart_id, bpm, format_version in that order')
    if records[4][1] != '2' or records[5] != HEADER:
        raise ValueError('Unsupported series version or V2 header; no V1 downgrade was attempted')
    meta = {name:records[i][1] for i,name in enumerate(names)}
    nominal = number(meta['bpm'],'nominal BPM')
    if nominal < 0: raise ValueError('BPM cannot be negative')
    notes=[]
    previous_index=-1
    combo=0
    count=0
    mean=0.0
    m2=0.0
    for cells in records[6:]:
        if len(cells) != 10: raise ValueError('Each V2 row must contain exactly ten cells')
        row=dict(zip(HEADER,cells))
        for key in ['note_index','time_ms','lane','nps','combo']:
            row[key]=integer(row[key],key)
        if row['note_index'] <= previous_index: raise ValueError('V2 note indexes must increase; gaps are allowed')
        previous_index=row['note_index']
        if row['judgement'] not in ('P','G','M'): raise ValueError('V2 judgement must be P, G or M')
        expected=0 if row['judgement']=='M' else combo+1
        if row['combo'] != expected: raise ValueError('V2 combo does not follow P/G increment and M reset rules')
        combo=row['combo']
        row['accuracy_delta']=number(row['accuracy_delta'],'accuracy_delta') if row['accuracy_delta'] else None
        latency=row['latency_ms']
        if latency and (not re.fullmatch(r'[+\-]?\d+',latency) or not -(2**63) <= int(latency) < 2**63):
            raise ValueError('V2 latency_ms must be a signed integer or blank')
        row['latency_ms']=int(latency) if latency else None
        row['bpm']=number(row['bpm'],'bpm')
        row['std_ms']=number(row['std_ms'],'std_ms') if row['std_ms'] else None
        if row['bpm'] < 0 or row['std_ms'] is not None and row['std_ms'] < 0:
            raise ValueError('V2 BPM and std_ms must be nonnegative')
        if row['judgement'] in ('P','G') and row['latency_ms'] is not None:
            count+=1
            delta=row['latency_ms']-mean
            mean+=delta/count
            m2+=delta*(row['latency_ms']-mean)
        if count < 2:
            if row['std_ms'] is not None: raise ValueError('V2 std_ms must be blank before two successful offsets')
        else:
            expected=math.floor(math.sqrt(max(0,m2/count))*10+.5)/10
            if row['std_ms'] is None or abs(row['std_ms']-expected) > .051:
                raise ValueError('V2 running population std_ms is inconsistent with successful offsets')
        notes.append(row)
        if len(notes) > 20000: raise ValueError('V2 exceeds 20,000 judged-note rows')
    return {'format_version':2,'game_id':integer(meta['game_id'],'game_id'),
            'song_id':integer(meta['song_id'],'song_id'),'chart_id':integer(meta['chart_id'],'chart_id'),
            'nominal_bpm':nominal,'notes':notes,'samples':[], 'sample_interval_sec':None,
            'successful_hit_count':count}


def analyze(run):
    notes=run['notes']
    # Engine-developer clarification: deltas start from a zero baseline.
    # Missing/partial rows still make this an estimate of captured judgements.
    estimate=math.fsum(n['accuracy_delta'] for n in notes) if notes and all(n['accuracy_delta'] is not None for n in notes) else None
    if estimate is not None and not -1e-9 <= estimate <= 100+1e-9: estimate=None
    if estimate is not None: estimate=min(100,max(0,estimate))
    partial=bool(notes) and (len(notes)!=run['summary']['total_notes'] or notes[0]['note_index']!=0 or any(b['note_index']!=a['note_index']+1 for a,b in zip(notes,notes[1:])))
    offsets=[r['latency_ms'] for r in notes if r['judgement'] in ('P','G') and r['latency_ms'] is not None]
    mean=sum(offsets)/len(offsets) if offsets else None
    spread=math.sqrt(sum((v-mean)**2 for v in offsets)/len(offsets)) if len(offsets)>=2 else None
    groups={}
    for row in notes: groups.setdefault(row['time_ms']//5000,[]).append(row)
    sections=[]
    for bucket, group in sorted(groups.items()):
        values=[r['latency_ms'] for r in group if r['judgement'] in ('P','G') and r['latency_ms'] is not None]
        avg=sum(values)/len(values) if values else None
        sd=math.sqrt(sum((v-avg)**2 for v in values)/len(values)) if len(values)>=2 else None
        sections.append({'start_ms':bucket*5000,'end_ms':(bucket+1)*5000,'accuracy':None,
                         'mean_offset_ms':avg,'spread_ms':sd,'judged_notes':len(group),
                         'misses':sum(r['judgement']=='M' for r in group),
                         'perfect':sum(r['judgement']=='P' for r in group),
                         'good':sum(r['judgement']=='G' for r in group),
                         'hit_rate':sum(r['judgement'] in ('P','G') for r in group)/len(group),
                         'measured_offsets':len(values)})
    tips=[]
    if mean is not None and abs(mean)>20:
        tips.append({'time_ms':0,'spans_song':True,'text':f"Successful P/G hits averaged {abs(mean):.2f} ms {'early' if mean<0 else 'late'}. Practice a steady beat and compare the next attempt."})
    flags=run.get('envelope',{})
    if flags.get('autoplay') or flags.get('summary_exceeds_format_range'): tips=[]
    spoken=f"Game score {run['summary']['score']}. "
    spoken+=(f"Approximately {estimate:.1f} percent accuracy from captured judgements. " if estimate is not None else "Accuracy is unavailable. ")
    spoken+=tips[0]['text'] if tips else 'Review the note-level result in the app.'
    return {'score':run['summary']['score'],'accuracy':estimate/100 if estimate is not None else None,'accuracy_is_approximate':estimate is not None,'accuracy_basis':'sum_of_rounded_v2_deltas_zero_baseline','accuracy_coverage_uncertain':partial,'grade':None,'mean_offset_ms':mean,
            'spread_ms':spread,'sections':sections,'tips':tips,'spoken_summary':spoken,
            'method':'note_level_v2','judgments':{j:sum(r['judgement']==j for r in notes) for j in ('P','G','M')}}
