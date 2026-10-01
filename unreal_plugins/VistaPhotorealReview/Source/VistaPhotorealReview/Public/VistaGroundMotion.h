#pragma once
#include <algorithm>
#include <cmath>
#include "VistaMotionCurves.h"

// Small deterministic controller, shared by the wearer and companion. Units:
// centimetres, seconds, degrees. Ground queries and limb IK stay in Unreal.
namespace VistaMotion
{
inline double AngleDelta(double From,double To)
{double A=std::fmod(To-From+540.0,360.0);if(A<0)A+=360.0;return A-180.0;}
inline double ArrivalSpeed(double Distance,double Limit,double Turn,double Brake=240.0)
{
    const double Alignment=std::max(0.0,std::cos(std::min(90.0,std::abs(Turn))*3.141592653589793/180.0));
    return std::min(Limit,std::sqrt(2*Brake*std::max(0.0,Distance)))*Alignment*Alignment;
}
inline double AdvanceHeading(double Yaw,double Goal,double Dt,double MaxRate,double& Rate)
{
    const double Error=AngleDelta(Yaw,Goal),Acceleration=480;
    const double Wanted=std::copysign(std::min(MaxRate,std::sqrt(2*Acceleration*std::abs(Error))),Error);
    Rate+=std::clamp(Wanted-Rate,-Acceleration*Dt,Acceleration*Dt);
    double Step=Rate*Dt;
    if (Step*Error>=0 && std::abs(Step)>=std::abs(Error)) {Step=Error;Rate=0;}
    return Yaw+Step;
}
struct GroundPoint {double X=0,Y=0,Z=0;};
inline double GroundDistance(GroundPoint A,GroundPoint B)
{return std::hypot(A.X-B.X,A.Y-B.Y);}
inline GroundPoint Mix(GroundPoint A,GroundPoint B,double T)
{return {A.X+(B.X-A.X)*T,A.Y+(B.Y-A.Y)*T,A.Z+(B.Z-A.Z)*T};}

struct TurnSteps
{
    GroundPoint Feet[2],Start;
    double Yaw[2]={0,0},StartYaw=0,Clock=0;
    int Swing=-1,Last=1,Count=0;
    bool Ready=false;
    static constexpr double Duration=.30,Lift=5.0;
    void Reset(const GroundPoint* Goals,double BodyYaw)
    {
        for(int S=0;S<2;++S){Feet[S]=Goals[S];Yaw[S]=BodyYaw;}
        Swing=-1;Clock=0;Ready=true;
    }
    void Update(double Dt,const GroundPoint* Goals,double BodyYaw,bool ResetNow)
    {
        if(!Ready || ResetNow){Reset(Goals,BodyYaw);return;}
        if(Swing<0)
        {
            double Need[2];for(int S=0;S<2;++S)
                Need[S]=std::max(GroundDistance(Feet[S],Goals[S])/5.0,std::abs(AngleDelta(Yaw[S],BodyYaw))/18.0);
            const int Next=1-Last;
            if(Need[Next]>1 || Need[Last]>1)
            {
                Swing=Need[Next]>1?Next:Last;Last=Swing;Start=Feet[Swing];StartYaw=Yaw[Swing];Clock=0;++Count;
            }
        }
        if(Swing>=0)
        {
            Clock=std::min(Duration,Clock+std::max(0.0,Dt));
            const double T=Clock/Duration,Blend=Ease(T);
            // The support foot is never interpolated. Only the swinging foot
            // catches up to the body, with zero lift velocity at either end.
            Feet[Swing]=Mix(Start,Goals[Swing],Blend);
            Feet[Swing].Z+=Lift*16*T*T*(1-T)*(1-T);
            Yaw[Swing]=StartYaw+AngleDelta(StartYaw,BodyYaw)*Blend;
            if(Clock>=Duration)Swing=-1;
        }
    }
};
}
