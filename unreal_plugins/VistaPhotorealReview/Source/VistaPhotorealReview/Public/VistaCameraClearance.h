#pragma once
#include <algorithm>
#include <cmath>

namespace VistaCamera
{
// Enclose all four perspective near-plane corners, including portrait windows.
inline float Clearance(float Near,float HorizontalFov,float Aspect)
{
    const float HalfWidth=Near*std::tan(std::clamp(HorizontalFov,20.f,120.f)*.00872664626f);
    const float HalfHeight=HalfWidth/std::max(.25f,Aspect);
    return std::max(6.f,std::sqrt(Near*Near+HalfWidth*HalfWidth+HalfHeight*HalfHeight)+1.f);
}
}
