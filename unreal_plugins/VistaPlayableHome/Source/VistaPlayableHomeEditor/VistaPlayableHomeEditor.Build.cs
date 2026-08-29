using UnrealBuildTool;

public class VistaPlayableHomeEditor : ModuleRules
{
    public VistaPlayableHomeEditor(ReadOnlyTargetRules Target) : base(Target)
    {
        PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;
        CppStandard = CppStandardVersion.Cpp20;

        PublicDependencyModuleNames.AddRange(new[]
        {
            "Core",
            "CoreUObject",
            "Engine"
        });

        PrivateDependencyModuleNames.AddRange(new[]
        {
            "AssetRegistry",
            "AssetTools",
            "CQTest",
            "EngineSettings",
            "Json",
            "LevelEditor",
            "MaterialEditor",
            "Slate",
            "UnrealEd",
            "VistaPlayableHome"
        });

        // PIENetworkComponent.h directly exposes Iris replication types.
        SetupIrisSupport(Target);
    }
}
