#pragma once

namespace VistaMotion
{
// Minimum-jerk interpolation: zero velocity and acceleration at both ends.
// Keep a single implementation shared by semantic actions and body reach.
inline float Ease(float T)
{
    if (T<=0.f) return 0.f;
    if (T>=1.f) return 1.f;
    return T*T*T*(10.f+T*(-15.f+6.f*T));
}
}
