// Lyris sailing (T21): a spot in a lit harbor where a swamped boat is brought home.

#include "Sailing/LyrisHarborMooring.h"

#include "Components/ArrowComponent.h"
#include "Components/SceneComponent.h"

ALyrisHarborMooring::ALyrisHarborMooring()
{
	PrimaryActorTick.bCanEverTick = false;

	RootComponent = CreateDefaultSubobject<USceneComponent>(TEXT("Root"));

#if WITH_EDITORONLY_DATA
	Arrow = CreateEditorOnlyDefaultSubobject<UArrowComponent>(TEXT("Arrow"));
	if (Arrow)
	{
		Arrow->SetupAttachment(RootComponent);
		Arrow->ArrowSize = 4.f;
		Arrow->bIsScreenSizeScaled = false;
	}
#endif
}
