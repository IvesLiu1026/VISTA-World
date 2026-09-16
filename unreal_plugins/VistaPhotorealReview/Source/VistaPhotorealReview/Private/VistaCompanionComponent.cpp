#include "VistaCompanion.h"
#include "VistaExplorer.h"
#include "HomeActionsJson.h"
#include "Components/SkeletalMeshComponent.h"
#include "Engine/Engine.h"
#include "Engine/GameViewportClient.h"
#include "Engine/World.h"
#include "Framework/Application/SlateApplication.h"
#include "Fonts/CompositeFont.h"
#include "GameFramework/PlayerController.h"
#include "HttpModule.h"
#include "Interfaces/IHttpRequest.h"
#include "Interfaces/IHttpResponse.h"
#include "Misc/CommandLine.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"
#include "TimerManager.h"
#include "Styling/CoreStyle.h"
#include "Widgets/Input/SButton.h"
#include "Widgets/Input/SEditableTextBox.h"
#include "Widgets/Layout/SBorder.h"
#include "Widgets/Layout/SBox.h"
#include "Widgets/SBoxPanel.h"
#include "Widgets/Text/STextBlock.h"

using namespace HomeJson;
namespace {
FSlateFontInfo CompanionFont(int32 Size)
{
    static const auto Font=MakeShared<FCompositeFont>(TEXT("Regular"),
        FPaths::ProjectContentDir()/TEXT("VISTA/Companion/Fonts/NotoSansCJK-Regular.ttc"),EFontHinting::Default,EFontLoadingPolicy::LazyLoad);
    return FSlateFontInfo(Font,Size,TEXT("Regular"));
}
}
UVistaCompanionComponent::UVistaCompanionComponent(){PrimaryComponentTick.bCanEverTick=true;}
void UVistaCompanionComponent::BeginPlay()
{
    Super::BeginPlay();
    if(!FPaths::FileExists(FPaths::ProjectConfigDir()/TEXT("VistaCompanion.json")))return;
    Session=FGuid::NewGuid().ToString(EGuidFormats::Digits);
    FParse::Value(FCommandLine::Get(),TEXT("VistaCompanionProof="),ProofDir);
    if(!ProofDir.IsEmpty())IFileManager::Get().MakeDirectory(*ProofDir,true);
    FTimerHandle Timer;GetWorld()->GetTimerManager().SetTimer(Timer,FTimerDelegate::CreateUObject(this,&UVistaCompanionComponent::Start),2.6f,false);
}
void UVistaCompanionComponent::Start()
{
    auto* Player=Cast<AVistaExplorerCharacter>(GetOwner());if(!Player || Player->bCampus || !Player->HasSceneReady())return;
    Player->HomeRoom(2);
    FActorSpawnParameters Args;Args.SpawnCollisionHandlingOverride=ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
    Companion=GetWorld()->SpawnActor<AVistaCompanion>(AVistaCompanion::StaticClass(),Player->GetActorTransform(),Args);
    if(!Companion)return;Companion->Leader=Player;
    if(!Companion->bReady || !Companion->PlaceNear(Player))
    {UE_LOG(LogTemp,Error,TEXT("VISTA_COMPANION_SPAWN_FAILED"));Companion->Destroy();Companion=nullptr;return;}
    LastRoom=String(Player->CompanionObservation(),TEXT("room"));
    if(GEngine && GEngine->GameViewport)
    {
        Captions=SNew(SVerticalBox)
        +SVerticalBox::Slot().FillHeight(1)
        +SVerticalBox::Slot().AutoHeight().HAlign(HAlign_Center).Padding(50,0,50,116)
        [SNew(SBox).MaxDesiredWidth(1060)
         [SNew(SBorder).BorderImage(FCoreStyle::Get().GetBrush("WhiteBrush")).Padding(FMargin(24,14)).BorderBackgroundColor(FLinearColor(.015,.025,.035,.94))
          .Visibility_Lambda([this]{return !bOpen && Companion && (Companion->bSpeaking || bBusy || GetWorld()->GetTimeSeconds()<NoticeUntil)?EVisibility::HitTestInvisible:EVisibility::Collapsed;})
          [SNew(STextBlock).Font(CompanionFont(22)).ColorAndOpacity(FLinearColor(.94,.97,1)).AutoWrapText(true)
           .Text_Lambda([this]{return FText::FromString(bBusy?TEXT("助手正在思考與準備語音……"):Reply);})]]];
        GEngine->GameViewport->AddViewportWidgetContent(Captions.ToSharedRef(),30);
    }
}
void UVistaCompanionComponent::TogglePanel()
{
    if(bOpen){ClosePanel();return;}if(!Companion || !GEngine || !GEngine->GameViewport)return;
    auto* P=Cast<AVistaExplorerCharacter>(GetOwner());if(!P)return;P->SetMenu(4);bOpen=true;
    PanelObservation=P->CompanionObservation();ObservationTime=GetWorld()->GetTimeSeconds();
    auto* PC=Cast<APlayerController>(P->GetController());
    if(PC)
    {
        FVector Eye;FRotator View;PC->GetPlayerViewPoint(Eye,View);
        const FVector Face=Companion->GetMesh()->GetBoneLocation(TEXT("head"));
        PC->SetControlRotation((Face-Eye).Rotation());
    }
    auto Rows=SNew(SVerticalBox);
    const auto Label=[&](const FString& Text,int32 Size){return SNew(STextBlock).Text(FText::FromString(Text)).Font(CompanionFont(Size)).AutoWrapText(true);};
    Rows->AddSlot().AutoHeight().Padding(0,0,0,8)[Label(TEXT("陪同助手"),26)];
    Rows->AddSlot().AutoHeight().Padding(0,0,0,16)
        [SNew(STextBlock).Font(CompanionFont(15)).ColorAndOpacity(FLinearColor(.48,.83,.76))
         .Text_Lambda([this]{return FText::FromString(Status+(Companion && Companion->bFollowing?TEXT(" · 陪同中"):TEXT(" · 原地等候")));})];
    Rows->AddSlot().AutoHeight().Padding(0,0,0,16)
        [SNew(STextBlock).Font(CompanionFont(20)).AutoWrapText(true).Text_Lambda([this]{return FText::FromString(Reply);})];
    Rows->AddSlot().AutoHeight().Padding(0,0,0,12)
        [SAssignNew(Entry,SEditableTextBox).Font(CompanionFont(18)).HintText(FText::FromString(TEXT("想問什麼？輸入後按 Enter")))
         .OnTextCommitted_Lambda([this](const FText& Text,ETextCommit::Type Type){if(Type==ETextCommit::OnEnter){Ask(Text.ToString());if(Entry)Entry->SetText(FText::GetEmpty());}})];
    const auto Button=[&](const FString& Text,TFunction<void()> Action)
    {
        Rows->AddSlot().AutoHeight().Padding(0,3)
            [SNew(SButton).ContentPadding(FMargin(12,9)).OnClicked_Lambda([Action]{Action();return FReply::Handled();})
             [Label(Text,17)]];
    };
    Button(TEXT("送出訊息"),[this]{if(Entry){Ask(Entry->GetText().ToString());Entry->SetText(FText::GetEmpty());}});
    Button(TEXT("介紹剛才看到的物件"),[this]{Ask(TEXT("請介紹我剛才看到的物件。"));});
    Button(TEXT("提醒我目前的任務"),[this]{Ask(TEXT("我目前有什麼任務？下一步可以怎麼做？"));});
    Button(TEXT("跟著我"),[this]{Follow(true);});
    Button(TEXT("在這裡等我"),[this]{Follow(false);});
    Button(TEXT("停止說話"),[this]{Stop();});
    Button(TEXT("繼續探索 · Esc"),[this]{ClosePanel();});
    Panel=SNew(SHorizontalBox)
        +SHorizontalBox::Slot().FillWidth(1)
        +SHorizontalBox::Slot().AutoWidth().VAlign(VAlign_Center).Padding(20)
        [SNew(SBox).WidthOverride(450)
         [SNew(SBorder).BorderImage(FCoreStyle::Get().GetBrush("WhiteBrush")).Padding(24).BorderBackgroundColor(FLinearColor(.025,.045,.055,.97))[Rows]]];
    GEngine->GameViewport->AddViewportWidgetContent(Panel.ToSharedRef(),40);
    if(Entry)FSlateApplication::Get().SetKeyboardFocus(Entry);
}
void UVistaCompanionComponent::ClosePanel()
{
    if(Panel && GEngine && GEngine->GameViewport)GEngine->GameViewport->RemoveViewportWidgetContent(Panel.ToSharedRef());
    Panel.Reset();Entry.Reset();PanelObservation.Reset();bOpen=false;
    if(auto* P=Cast<AVistaExplorerCharacter>(GetOwner()))P->SetMenu(0);
    if(FSlateApplication::IsInitialized())FSlateApplication::Get().SetAllUserFocusToGameViewport();
}
void UVistaCompanionComponent::Ask(const FString& Text)
{
    const FString Question=Text.TrimStartAndEnd().Left(600);if(Question.IsEmpty() || !Companion)return;
    if(bBusy){Status=TEXT("正在回應；可先按「停止說話」");return;}
    auto* P=Cast<AVistaExplorerCharacter>(GetOwner());if(!P)return;
    if(Question==TEXT("跟著我") || Question==TEXT("請跟著我"))Follow(true);
    if(Question==TEXT("在這裡等我") || Question==TEXT("請在這裡等我"))Follow(false);
    Companion->StopSpeech();bBusy=true;LastQuestion=Question;Status=TEXT("思考與準備語音中……");
    auto Body=MakeShared<FJsonObject>();Body->SetStringField(TEXT("session"),Session);Body->SetStringField(TEXT("text"),Question);
    auto Obs=bOpen && PanelObservation?PanelObservation:P->CompanionObservation();
    Obs->SetNumberField(TEXT("observed_seconds_ago"),bOpen?FMath::Max(0.0,GetWorld()->GetTimeSeconds()-ObservationTime):0);
    Obs->SetBoolField(TEXT("following"),Companion->bFollowing);Body->SetObjectField(TEXT("observation"),Obs);
    const int32 Ticket=++Serial;TWeakObjectPtr<UVistaCompanionComponent> Weak(this);
    Pending=FHttpModule::Get().CreateRequest();Pending->SetURL(Endpoint+TEXT("/respond"));Pending->SetVerb(TEXT("POST"));
    Pending->SetHeader(TEXT("Content-Type"),TEXT("application/json"));Pending->SetContentAsString(Encode(Body));Pending->SetTimeout(210);
    Pending->OnProcessRequestComplete().BindLambda([Weak,Ticket](FHttpRequestPtr Request,FHttpResponsePtr Response,bool Ok)
    {
        auto* Self=Weak.Get();if(!Self || Ticket!=Self->Serial)return;
        Self->bBusy=false;Self->Pending.Reset();
        if(!Ok || !Response || Response->GetResponseCode()!=200)
        {Self->Status=TEXT("暫時無法回應，請稍後再試");return;}
        const auto Data=Decode(Response->GetContentAsString());
        if(!Data || !Data->HasField(TEXT("pcm_b64")) || !Data->HasField(TEXT("mouth")))
        {Self->Status=TEXT("語音資料不完整，請重試");return;}
        Self->Reply=String(Data,TEXT("text"));Self->Status=TEXT("正在說話");
        if(Self->Companion)Self->Companion->Speak(Data);
        if(!Self->ProofDir.IsEmpty())
        {
            Data->RemoveField(TEXT("pcm_b64"));Data->RemoveField(TEXT("mouth"));
            FFileHelper::SaveStringToFile(Encode(Data),*(Self->ProofDir/TEXT("last-response.json")),FFileHelper::EEncodingOptions::ForceUTF8WithoutBOM);
        }
    });
    if(!Pending->ProcessRequest()){Pending.Reset();bBusy=false;Status=TEXT("無法連線到本機助手");}
}
void UVistaCompanionComponent::Stop()
{
    ++Serial;
    if(Pending){Pending->OnProcessRequestComplete().Unbind();Pending->CancelRequest();Pending.Reset();}
    if(bBusy)
    {
        auto Request=FHttpModule::Get().CreateRequest();Request->SetURL(Endpoint+TEXT("/cancel/")+Session);
        Request->SetVerb(TEXT("POST"));Request->SetTimeout(5);Request->ProcessRequest();
    }
    bBusy=false;if(Companion)Companion->StopSpeech();Status=TEXT("已停止說話");
}
void UVistaCompanionComponent::Follow(bool Enabled)
{
    if(!Companion)return;Companion->bFollowing=Enabled;Status=Enabled?TEXT("我會跟著你"):TEXT("我在這裡等你");
}
TSharedPtr<FJsonObject> UVistaCompanionComponent::State() const
{
    auto D=MakeShared<FJsonObject>();D->SetStringField(TEXT("schema"),TEXT("vista.companion-runtime/v1"));
    D->SetBoolField(TEXT("enabled"),Companion!=nullptr);D->SetBoolField(TEXT("panel"),bOpen);D->SetBoolField(TEXT("busy"),bBusy);
    D->SetStringField(TEXT("status"),Status);D->SetStringField(TEXT("reply"),Reply);D->SetStringField(TEXT("question"),LastQuestion);
    if(Companion)
    {
        D->SetBoolField(TEXT("ready"),Companion->bReady);D->SetBoolField(TEXT("following"),Companion->bFollowing);
        D->SetBoolField(TEXT("speaking"),Companion->bSpeaking);D->SetBoolField(TEXT("blocked"),Companion->bBlocked);
        D->SetNumberField(TEXT("audio_clock"),Companion->AudioClock);D->SetNumberField(TEXT("mouth_open"),Companion->MouthOpen);
        D->SetNumberField(TEXT("travel_cm"),Companion->Travel);D->SetNumberField(TEXT("yaw"),Companion->GetActorRotation().Yaw);
        D->SetNumberField(TEXT("speed_cm_s"),Companion->GetVelocity().Size2D());
        const auto V=Companion->GetActorLocation();D->SetArrayField(TEXT("position_cm"),{MakeShared<FJsonValueNumber>(V.X),MakeShared<FJsonValueNumber>(V.Y),MakeShared<FJsonValueNumber>(V.Z)});
        D->SetNumberField(TEXT("distance_cm"),FVector::Dist2D(V,GetOwner()->GetActorLocation()));
    }
    if(auto* P=Cast<AHomeActionsCharacter>(GetOwner()))D->SetObjectField(TEXT("observation"),P->CompanionObservation());
    return D;
}
void UVistaCompanionComponent::TickComponent(float Dt,ELevelTick Tick,FActorComponentTickFunction* ThisTick)
{
    Super::TickComponent(Dt,Tick,ThisTick);if(!Companion)return;
    if(Status==TEXT("正在說話") && !Companion->bSpeaking)Status=TEXT("準備好了");
    PublishClock+=Dt;if(PublishClock<.1f)return;PublishClock=0;
    if(auto* P=Cast<AVistaExplorerCharacter>(GetOwner()))
    {
        const FString Room=String(P->CompanionObservation(),TEXT("room"));
        LastRoom=Room;
    }
    if(!ProofDir.IsEmpty())
    {
        const FString Temp=ProofDir/TEXT("state.tmp"),File=ProofDir/TEXT("state.json");
        if(FFileHelper::SaveStringToFile(Encode(State()),*Temp,FFileHelper::EEncodingOptions::ForceUTF8WithoutBOM))IFileManager::Get().Move(*File,*Temp,true);
    }
}
void UVistaCompanionComponent::EndPlay(const EEndPlayReason::Type Reason)
{
    Stop();ClosePanel();
    if(Captions && GEngine && GEngine->GameViewport)GEngine->GameViewport->RemoveViewportWidgetContent(Captions.ToSharedRef());
    Captions.Reset();if(Companion)Companion->Destroy();Companion=nullptr;Super::EndPlay(Reason);
}
