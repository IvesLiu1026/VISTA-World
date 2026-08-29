using UnrealBuildTool;

public class VistaR5ProofTarget : TargetRules
{
    public VistaR5ProofTarget(TargetInfo Target) : base(Target)
    {
        Type = TargetType.Game;
        DefaultBuildSettings = BuildSettingsVersion.V6;
        IncludeOrderVersion = EngineIncludeOrderVersion.Unreal5_7;
        ExtraModuleNames.Add("VistaR5Proof");
    }
}
