"""Render standalone views of the Mermaid architecture/state diagrams in the guide."""
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch,FancyArrowPatch

output=Path(__file__).resolve().parents[1]/'docs/evidence'
output.mkdir(parents=True,exist_ok=True)
def box(ax,x,y,w,h,text,color='#eaf2f7',size=11):
    ax.add_patch(FancyBboxPatch((x,y),w,h,boxstyle='round,pad=0.008',facecolor=color,edgecolor='#385b74',linewidth=1.5))
    ax.text(x+w/2,y+h/2,text,ha='center',va='center',fontsize=size,color='#16354b')
def arrow(ax,start,end,style='->',rad=0):
    ax.add_patch(FancyArrowPatch(start,end,arrowstyle=style,mutation_scale=14,
                               connectionstyle=f'arc3,rad={rad}',linewidth=1.5,color='#385b74'))
fig,ax=plt.subplots(figsize=(12,5.2));ax.set(xlim=(0,1),ylim=(0,1));ax.axis('off')
ax.add_patch(FancyBboxPatch((.26,.1),.48,.8,boxstyle='round,pad=.008',facecolor='#f8fafc',edgecolor='#8b9fae',linestyle='--'))
ax.text(.5,.85,'Single laptop during development',ha='center',fontsize=12,weight='bold')
box(ax,.30,.65,.40,.15,'Operator browser\nHTTP controls + live status')
box(ax,.30,.25,.40,.20,'Python gateway\nBounded queue · jobs · states · batch counts')
box(ax,.015,.27,.21,.16,'ESP32 A\nVirtual production')
box(ax,.78,.27,.205,.16,'ESP32 B\nInspection + PASS/FAIL')
arrow(ax,(.39,.64),(.39,.46));arrow(ax,(.61,.46),(.61,.64))
ax.text(.36,.545,'HTTP\ncmd_id',ha='right',va='center',fontsize=10)
ax.text(.64,.545,'WebSocket\nstatus',ha='left',va='center',fontsize=10)
arrow(ax,(.23,.35),(.29,.35),'<->');arrow(ax,(.71,.35),(.77,.35),'<->')
ax.text(.19,.49,'USB serial (wired)',ha='center',fontsize=10)
ax.text(.17,.20,'SLIP + ATR + CRC',ha='center',fontsize=10)
ax.text(.84,.49,'Wi-Fi TCP',ha='center',fontsize=10)
ax.text(.86,.20,'Length-prefixed frames',ha='center',fontsize=10)
ax.text(.5,.025,"B's USB is for power, provisioning and serial evidence; operational inspection uses Wi-Fi TCP.",ha='center',fontsize=10)
fig.suptitle('Milestone 1 architecture',fontsize=16);fig.tight_layout()
for ext in ('png','svg'):fig.savefig(output/f'architecture.{ext}',dpi=160)
plt.close(fig)
fig,ax=plt.subplots(figsize=(11,6));ax.set(xlim=(0,1),ylim=(0,1));ax.axis('off')
box(ax,.05,.65,.20,.15,'Idle');box(ax,.40,.65,.20,.15,'Running',color='#e4f3ee')
box(ax,.75,.65,.20,.15,'Paused',color='#fff3db');box(ax,.40,.15,.20,.15,'Fault',color='#fae6e9')
arrow(ax,(.26,.725),(.39,.725));ax.text(.325,.76,'Start',ha='center',fontsize=11)
arrow(ax,(.61,.76),(.74,.76),rad=-.3);ax.text(.675,.85,'Pause',ha='center',fontsize=11)
arrow(ax,(.74,.69),(.61,.69),rad=-.3);ax.text(.675,.59,'Resume',ha='center',fontsize=11)
arrow(ax,(.40,.65),(.25,.65),rad=-.4);ax.text(.32,.52,'Complete / Stop',ha='center',fontsize=10)
arrow(ax,(.50,.64),(.50,.31));ax.text(.53,.46,'Full queue, timeout,\ndisconnection or invalid result',va='center',fontsize=10)
arrow(ax,(.41,.18),(.15,.64),rad=-.3);ax.text(.16,.30,'Stop + explicit\nreset / reconnect',ha='center',fontsize=10)
ax.text(.5,.05,'Stop from Running or Paused aborts remaining work. A connected device failure can fault any state.',ha='center',fontsize=10)
fig.suptitle('Gateway operating states',fontsize=16);fig.tight_layout()
for ext in ('png','svg'):fig.savefig(output/f'states.{ext}',dpi=160)
print('Architecture and state diagrams saved:',output)
