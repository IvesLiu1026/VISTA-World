using UnrealBuildTool;

public class VistaR5ProofEditorTarget : TargetRules
{
    public VistaR5ProofEditorTarget(TargetInfo Target) : base(Target)
    {
        Type = TargetType.Editor;
        DefaultBuildSettings = BuildSettingsVersion.V6;
        IncludeOrderVersion = EngineIncludeOrderVersion.Unreal5_7;
        ExtraModuleNames.Add("VistaR5Proof");
    }
}
