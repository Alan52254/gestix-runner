using UnityEngine;
using TMPro;
using System.Collections.Generic;

public class ResolutionSettings : MonoBehaviour
{
    [Header("UI")]
    public TMP_Dropdown resolutionDropdown;    // 解析度下拉
    public TMP_Dropdown displayModeDropdown;   // 顯示模式下拉

    // 預設幾個常用解析度
    private readonly (int w, int h, string label)[] presets = new (int, int, string)[]
    {
        (1920, 1080, "1920 x 1080"),
        (2560, 1440, "2560 x 1440"),
    };

    private void Start()
    {
        SetupResolutionDropdown();
        SetupDisplayModeDropdown();
    }

    // ----------------- 解析度 Dropdown 初始化 -----------------
    private void SetupResolutionDropdown()
    {
        if (resolutionDropdown == null)
        {
            Debug.LogWarning("[ResolutionSettings] resolutionDropdown 沒有指定");
            return;
        }

        resolutionDropdown.ClearOptions();

        List<string> options = new List<string>();
        Resolution current = Screen.currentResolution;

        int closestIndex = 0;
        for (int i = 0; i < presets.Length; i++)
        {
            options.Add(presets[i].label);

            if (Mathf.Abs(presets[i].w - current.width) <= 1 &&
                Mathf.Abs(presets[i].h - current.height) <= 1)
            {
                closestIndex = i;
            }
        }

        resolutionDropdown.AddOptions(options);

        // 顯示最接近目前解析度的選項
        resolutionDropdown.value = closestIndex;
        resolutionDropdown.RefreshShownValue();
    }

    // ----------------- 顯示模式 Dropdown 初始化 -----------------
    private void SetupDisplayModeDropdown()
    {
        if (displayModeDropdown == null)
        {
            Debug.LogWarning("[ResolutionSettings] displayModeDropdown 沒有指定");
            return;
        }

        displayModeDropdown.ClearOptions();

        List<string> modeOptions = new List<string>
        {
            "Windowed",
            "FullScreen",
            "FullScreenWindow"
        };

        displayModeDropdown.AddOptions(modeOptions);

        // 根據目前螢幕模式選一個預設
        FullScreenMode mode = Screen.fullScreenMode;
        int defaultIndex = 0;

        switch (mode)
        {
            case FullScreenMode.ExclusiveFullScreen:
                defaultIndex = 1; // 全螢幕
                break;
            case FullScreenMode.FullScreenWindow:
                defaultIndex = 2; // 偽全螢幕
                break;
            default:
                defaultIndex = 0; // 視窗模式
                break;
        }

        displayModeDropdown.value = defaultIndex;
        displayModeDropdown.RefreshShownValue();
    }

    // ----------------- ★ 按下 Apply 時才讀 Dropdown 並套用 -----------------
    public void ApplySettings()
    {
        int resIndex = (resolutionDropdown != null) ? resolutionDropdown.value : 0;
        int modeIndex = (displayModeDropdown != null) ? displayModeDropdown.value : 0;

        ApplyResolutionAndMode(resIndex, modeIndex);
    }

    private void ApplyResolutionAndMode(int resIndex, int modeIndex)
    {
        if (resIndex < 0 || resIndex >= presets.Length)
            return;

        var p = presets[resIndex];

        FullScreenMode modeToUse = FullScreenMode.Windowed;

        switch (modeIndex)
        {
            case 0: // 視窗模式
                modeToUse = FullScreenMode.Windowed;
                break;
            case 1: // 真全螢幕
                modeToUse = FullScreenMode.ExclusiveFullScreen;
                break;
            case 2: // 偽全螢幕（無邊框）
                modeToUse = FullScreenMode.FullScreenWindow;
                break;
        }

        Screen.SetResolution(p.w, p.h, modeToUse);
        Debug.Log($"[ResolutionSettings] Apply → 解析度：{p.w} x {p.h}，模式：{modeToUse}");
    }
}
