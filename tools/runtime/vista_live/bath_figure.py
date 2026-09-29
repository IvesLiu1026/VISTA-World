# /// script
# requires-python = ">=3.10"
# dependencies = ["matplotlib>=3.9,<4"]
# ///
"""Standalone scientific figure from measured native bath traces."""
import argparse
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt


def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();a.out.mkdir(exist_ok=True,parents=True)
    runs={}
    for file in sorted(a.root.glob('*/result.json'),key=lambda p:p.stat().st_mtime):
        r=json.loads(file.read_text())
        if r['status']=='completed':runs[r['condition']]=(r,json.loads((file.parent/'trace.json').read_text()))
    plt.rcParams.update({'font.size':13,'axes.labelsize':15})
    fig,ax=plt.subplots(figsize=(13.5,4.5),layout='constrained')
    fig.set_facecolor('#f4f3ef');ax.set_facecolor('#ffffff')
    for key,label,color,style in [('control','A No assistance','#a44635','-'),('timely','B Timely reference','#087e8b','-'),
                                  ('late','C Late reference','#bd8029','--'),('model','D Model rollout','#436ebd',':')]:
        if key not in runs:continue
        r,rows=runs[key];m=r['metrics']
        ax.plot([v['t'] for v in rows],[v['level'] for v in rows],label=label,color=color,ls=style,lw=2.7)
        if m['commit_s'] is not None:
            ax.scatter([m['commit_s']],[m['final_level']],s=60,color=color,zorder=5)
            ax.annotate(f"off @ {m['commit_s']:.2f}s",(m['commit_s'],m['final_level']),
                        xytext=(8,-24 if key=='late' else 14),textcoords='offset points',color=color,fontsize=10)
    ax.axhline(1,color='#5a6873',ls=':',lw=1)
    ax.text(2,1.009,'Full level / overflow threshold',fontsize=10,color='#526771')
    ax.set(xlim=(0,140),ylim=(.73,1.055),xlabel='Native time since bath event (s)',ylabel='Normalized water level')
    ax.grid(alpha=.18);ax.legend(loc='lower right',frameon=True,fontsize=11)
    ax.set_title('Same initial bath, different intervention timing',loc='left',fontsize=17,pad=15)
    fig.supxlabel('One pilot per condition · dots = actual committed shutoffs · no volume / fluid-fidelity claim',fontsize=10,color='#526771')
    for ext in ['png','pdf','svg']:fig.savefig(a.out/('bath-results.'+ext),dpi=180)
    (a.out/'figure-provenance.json').write_text(json.dumps({k:r['run_id'] for k,(r,_) in runs.items()},indent=2))


if __name__=='__main__':main()
