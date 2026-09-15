#pragma once
#include <algorithm>
#include <cmath>

namespace VistaMotion
{
// Continuous anatomical offset; a wrapped camera target must never directly
// replace a joint angle. Independent of UE so the exact update is testable.
struct BodyLook
{
    float Yaw=0,Pitch=0;
    static float Delta(float From,float To)
    {
        float D=std::fmod(To-From+180.f,360.f);if (D<0) D+=360.f;return D-180.f;
    }
    static float Approach(float Value,float Target,float Limit)
    {return Value+std::clamp(Target-Value,-Limit,Limit);}
    void Update(float RelativeYaw,float CameraPitch,float Dt,bool Active)
    {
        const float H=std::clamp(Dt,0.f,.1f);
        const float TargetYaw=Active?std::clamp(Delta(0,RelativeYaw),-65.f,65.f):0.f;
        const float TargetPitch=Active?std::clamp(Delta(0,CameraPitch),-50.f,40.f):0.f;
        Yaw=Approach(Yaw,TargetYaw,180.f*H);Pitch=Approach(Pitch,TargetPitch,140.f*H);
    }
};
}
