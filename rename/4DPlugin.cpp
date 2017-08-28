/* --------------------------------------------------------------------------------
 #
 #	4DPlugin.cpp
 #	source generated by 4D Plugin Wizard
 #	Project : RENAME
 #	author : miyako
 #	2017/08/28
 #
 # --------------------------------------------------------------------------------*/


#include "4DPluginAPI.h"
#include "4DPlugin.h"

void PluginMain(PA_long32 selector, PA_PluginParameters params)
{
	try
	{
		PA_long32 pProcNum = selector;
		sLONG_PTR *pResult = (sLONG_PTR *)params->fResult;
		PackagePtr pParams = (PackagePtr)params->fParameters;

		CommandDispatcher(pProcNum, pResult, pParams); 
	}
	catch(...)
	{

	}
}

void CommandDispatcher (PA_long32 pProcNum, sLONG_PTR *pResult, PackagePtr pParams)
{
	switch(pProcNum)
	{
// --- RENAME

		case 1 :
			RENAME(pResult, pParams);
			break;

	}
}

// ------------------------------------ RENAME ------------------------------------


void RENAME(sLONG_PTR *pResult, PackagePtr pParams)
{
	C_TEXT Param1;
	C_TEXT Param2;
	C_LONGINT Param3;

	Param1.fromParamAtIndex(pParams, 1);
	Param2.fromParamAtIndex(pParams, 2);

#if VERSIONWIN
	Param3.setIntValue(
		_wrename((const wchar_t *)Param1.getUTF16StringPtr(), (const wchar_t *)Param2.getUTF16StringPtr())
	);
#else
	CUTF8String oldName, newName;
	Param1.copyPath(&oldName);
	Param2.copyPath(&newName);
	Param3.setIntValue(
		rename((const char *)oldName.c_str(), (const char *)newName.c_str())
	);
#endif

	Param3.toParamAtIndex(pParams, 3);
}

