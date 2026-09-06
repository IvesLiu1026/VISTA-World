using UnrealBuildTool;

public class VistaPhotorealReview : ModuleRules
{
    public VistaPhotorealReview(ReadOnlyTargetRules Target) : base(Target)
    {
        PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;
        PublicDependencyModuleNames.AddRange(new[] { "Core", "CoreUObject", "Engine", "InputCore", "Json", "JsonUtilities", "PhysicsCore" });
    }
}
