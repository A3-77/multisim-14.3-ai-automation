import math
R=1000.0;C=100e-9;f=2000.0
w=2*math.pi*f; x=w*R*C
g=1/math.sqrt(1+x*x); p=-math.degrees(math.atan(x))
runs=[("s-696622ee67",0.6214528130301648,-51.57825257958607,0.6194584914299128,0.9967908720365626),
      ("s-36d69b98c4",0.6214495227413437,-51.5780054035858,0.619454833464225,0.9967902634017327)]
print("theory gain %.6f phase %.4f amp %.6f"%(g,p,g))
for sid,gm,pm,am,am_in in runs:
    print(sid,"gain %.6f d=%.6f rel=%.4f%% | phase %.4f d=%.4f | amp %.6f d=%.6f rel=%.4f%% | Vin amp %.6f err %.4f%%"%(
      gm,gm-g,(gm-g)/g*100,pm,pm-p,am,am-g,(am-g)/g*100,am_in,(am_in-1)*100))
