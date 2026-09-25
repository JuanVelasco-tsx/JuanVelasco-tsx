from PIL import Image, ImageOps
import numpy as np, random
random.seed(7)
N=240; PX=2           # rejilla 240x240, píxel de 2 unidades -> 480x480
OX,OY=20,56           # offset del retrato dentro del SVG
W,H=520,590
DUR=12.0
v1=Image.open('/mnt/user-data/uploads/img_propia_v1.png').convert('RGBA')
v3=Image.open('/mnt/user-data/uploads/img_propia_v3_gpt.png').convert('RGBA')
# alinear v3 al encuadre de v1 (parámetros obtenidos por registro)
sc,dx,dy=0.84,96,50
s=v3.resize((int(1254*sc),)*2,Image.LANCZOS)
v3a=Image.new('RGBA',v1.size,(0,0,0,0)); v3a.paste(s,(dx,dy),s)

def dither(im,gamma,lo=0.15,hi=0.90):
    im=im.resize((N,N),Image.LANCZOS)
    a=np.array(im)[...,3]/255.
    g=np.array(ImageOps.grayscale(im.convert('RGB')),float)/255.
    g=np.clip((g-lo)/(hi-lo),0,1)**gamma*a
    lv=np.array([0,.33,.66,1.]); e=g.copy(); q=np.zeros((N,N),int)
    for y in range(N):
        for x in range(N):
            o=e[y,x]; i=int(np.abs(lv-o).argmin()); q[y,x]=i; err=o-lv[i]
            if x+1<N: e[y,x+1]+=err*7/16
            if y+1<N:
                if x>0: e[y+1,x-1]+=err*3/16
                e[y+1,x]+=err*5/16
                if x+1<N: e[y+1,x+1]+=err/16
    q[a<0.5]=0
    return q
q1=dither(v1,0.9); q3=dither(v3a,0.72)   # v3 con sombras levantadas
COL={1:'#7E22CE',2:'#A855F7',3:'#E9D5FF'}

def runs(q,rows=None):
    out=[]
    for y in (rows if rows is not None else range(N)):
        x=0
        while x<N:
            t=q[y,x]
            if t==0: x+=1; continue
            x0=x
            while x<N and q[y,x]==t and x-x0<6: x+=1
            out.append((y,x0,x-x0,t))
    return out
def pathd(rs):
    return ''.join(f'M{x*PX} {y*PX}h{l*PX}v{PX}h-{l*PX}z' for y,x,l,t in rs)
def kt(pairs):
    ts=';'.join(f'{t/DUR:.4f}' for t,_ in pairs); vs=';'.join(str(v) for _,v in pairs); return ts,vs
def anim(attr,pairs,extra=''):
    ts,vs=kt(pairs)
    return f'<animate attributeName="{attr}" values="{vs}" keyTimes="{ts}" dur="{DUR}s" repeatCount="indefinite" {extra}/>'

# línea de tiempo
T_REVEAL0,T_REVEAL1=0.2,2.2; T_HIT=4.2; T_CRACK=5.4; T_DISS0,T_DISS1=8.4,10.2
CX,CY=122*PX,177*PX       # centro de la grieta (estrella en la espalda)
RMAX=560

svg=[f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" font-family="ui-monospace,SFMono-Regular,Menlo,Consolas,monospace">']
svg.append(f'''<defs>
<linearGradient id="bd" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#A855F7"><animate attributeName="stop-color" values="#A855F7;#7E22CE;#C084FC;#A855F7" dur="8s" repeatCount="indefinite"/></stop><stop offset="1" stop-color="#7E22CE"><animate attributeName="stop-color" values="#7E22CE;#C084FC;#A855F7;#7E22CE" dur="8s" repeatCount="indefinite"/></stop></linearGradient>
<filter id="gl" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="6"/></filter>
<mask id="m1" maskUnits="userSpaceOnUse" x="0" y="0" width="{W}" height="{H}"><circle cx="{CX}" cy="{CY}" r="0" fill="#fff">{anim('r',[(0,0),(T_HIT,0),(T_CRACK,RMAX),(DUR,RMAX)],'calcMode="spline" keySplines="0 0 1 1;.2 .8 .3 1;0 0 1 1"')}</circle></mask>
<mask id="m3" maskUnits="userSpaceOnUse" x="0" y="0" width="{W}" height="{H}"><rect x="0" y="0" width="{W}" height="{H}" fill="#fff"/><circle cx="{CX}" cy="{CY}" r="0" fill="#000">{anim('r',[(0,0),(T_HIT,0),(T_CRACK,RMAX),(DUR,RMAX)],'calcMode="spline" keySplines="0 0 1 1;.2 .8 .3 1;0 0 1 1"')}</circle></mask>
<clipPath id="panel"><rect x="{OX-4}" y="{OY-4}" width="{N*PX+8}" height="{N*PX+8}" rx="8"/></clipPath>
</defs>''')
svg.append(f'<rect x="1.5" y="1.5" width="{W-3}" height="{H-3}" rx="16" fill="#0D0818" stroke="url(#bd)" stroke-width="2"/>')
svg.append(f'<text x="22" y="34" font-size="11" letter-spacing="3" fill="#6B4F8F">VISUAL.MAP</text>')
svg.append(f'<text x="{W-22}" y="34" font-size="11" text-anchor="end" fill="#C084FC">● <tspan>LIVE</tspan>{anim("opacity",[(0,1),(1,0.3),(2,1),(DUR,1)])}</text>')
svg.append(f'<g clip-path="url(#panel)"><g transform="translate({OX},{OY})">')
# sacudida en el impacto
shake=[(0,'0 0'),(T_HIT,'0 0'),(T_HIT+.05,'-4 2'),(T_HIT+.1,'4 -3'),(T_HIT+.15,'-3 -1'),(T_HIT+.2,'2 3'),(T_HIT+.3,'0 0'),(DUR,'0 0')]
ts,vs=kt(shake)
svg.append(f'<g><animateTransform attributeName="transform" type="translate" values="{vs}" keyTimes="{ts}" dur="{DUR}s" repeatCount="indefinite"/>')

# --- v3: aparición por bandas (escaneo)
svg.append('<g mask="url(#m3)">')
B=30; bh=N//B
for b in range(B):
    t=T_REVEAL0+(T_REVEAL1-T_REVEAL0)*b/B
    rs=runs(q3,range(b*bh,(b+1)*bh))
    if not rs: continue
    svg.append(f'<g opacity="0">{anim("opacity",[(0,0),(t,0),(t+.12,1),(DUR,1)])}')
    for tone in (1,2,3):
        d=pathd([r for r in rs if r[3]==tone])
        if d: svg.append(f'<path fill="{COL[tone]}" d="{d}"/>')
    svg.append('</g>')
svg.append('</g>')

# --- v1: grietas, revelado radial y disolución por grupos
svg.append('<g mask="url(#m1)">')
G=10; rs1=runs(q1); groups={g:[] for g in range(G)}
for r in rs1: groups[random.randrange(G)].append(r)
for g in range(G):
    t=T_DISS0+(T_DISS1-T_DISS0)*g/G
    svg.append(f'<g>{anim("opacity",[(0,1),(t,1),(t+.35,0),(DUR-.01,0),(DUR,1)])}')
    for tone in (1,2,3):
        d=pathd([r for r in groups[g] if r[3]==tone])
        if d:
            extra=anim("opacity",[(0,1),(T_CRACK,1),(T_CRACK+.8,.75),(T_CRACK+1.6,1),(T_CRACK+2.4,.75),(T_CRACK+3,1),(DUR,1)]) if tone==3 else ''
            svg.append(f'<path fill="{COL[tone]}" d="{d}">{extra}</path>')
    svg.append('</g>')
svg.append('</g>')
# frente de la grieta: anillo + destello
ring=[(0,0),(T_HIT,0),(T_CRACK,RMAX),(DUR,RMAX)]
svg.append(f'<circle cx="{CX}" cy="{CY}" r="0" fill="none" stroke="#E9D5FF" stroke-width="3" stroke-dasharray="2 4" opacity="0">{anim("r",ring,"calcMode=\"spline\" keySplines=\"0 0 1 1;.2 .8 .3 1;0 0 1 1\"")}{anim("opacity",[(0,0),(T_HIT,0),(T_HIT+.05,.9),(T_CRACK,0),(DUR,0)])}</circle>')
svg.append(f'<circle cx="{CX}" cy="{CY}" r="38" fill="#E9D5FF" filter="url(#gl)" opacity="0">{anim("opacity",[(0,0),(T_HIT,0),(T_HIT+.05,.55),(T_HIT+.3,0),(DUR,0)])}</circle>')
svg.append('</g></g></g>')
# esquinas tipo visor
x0,y0,x1,y1=OX-6,OY-6,OX+N*PX+6,OY+N*PX+6; L=16
for (x,y,sx,sy) in [(x0,y0,1,1),(x1,y0,-1,1),(x0,y1,1,-1),(x1,y1,-1,-1)]:
    svg.append(f'<path d="M{x} {y+sy*L}V{y}H{x+sx*L}" fill="none" stroke="#A855F7" stroke-width="2"/>')
# pie: estado
svg.append(f'<text x="22" y="{H-16}" font-size="11" fill="#6B4F8F">status: <tspan fill="#C084FC">stable</tspan>{anim("opacity",[(0,1),(T_HIT,1),(T_HIT+.01,0),(DUR,0)])}</text>')
svg.append(f'<text x="22" y="{H-16}" font-size="11" fill="#6B4F8F" opacity="0">status: <tspan fill="#E9D5FF">fractured</tspan>{anim("opacity",[(0,0),(T_HIT,0),(T_HIT+.01,1),(T_DISS0,1),(T_DISS0+.01,0),(DUR,0)])}</text>')
svg.append(f'<text x="22" y="{H-16}" font-size="11" fill="#6B4F8F" opacity="0">status: <tspan fill="#A855F7">dissolving → particles</tspan>{anim("opacity",[(0,0),(T_DISS0,0),(T_DISS0+.01,1),(DUR-.5,1),(DUR-.49,0),(DUR,0)])}</text>')
svg.append('</svg>')
open('/mnt/user-data/outputs/banner_transicion_proto.svg','w').write('\n'.join(svg))
import os; print(os.path.getsize('/mnt/user-data/outputs/banner_transicion_proto.svg')//1024,'KB')
