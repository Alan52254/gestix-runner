using UnityEngine;
using UnityEngine.SceneManagement;
using UnityEngine.InputSystem;

public class PauseManager : MonoBehaviour
{
    public GameObject pausePanel;    // 暫停介面
    public PlayerInput playerInput;  // 玩家操作
    private bool isPaused = false;

    void Update()
    {
        if (Keyboard.current.escapeKey.wasPressedThisFrame)
        {
            if (isPaused)
                ResumeGame();
            else
                PauseGame();
        }
    }

    public void PauseGame()
    {
        isPaused = true;

        // 顯示介面
        pausePanel.SetActive(true);

        // 停止遊戲
        Time.timeScale = 0f;

        // 停止玩家輸入
        if (playerInput != null)
            playerInput.enabled = false;

        // 解鎖滑鼠
        Cursor.lockState = CursorLockMode.None;
        Cursor.visible = true;
    }

    public void ResumeGame()
    {
        isPaused = false;

        pausePanel.SetActive(false);
        Time.timeScale = 1f;

        // 開啟玩家輸入
        if (playerInput != null)
            playerInput.enabled = true;

        Cursor.lockState = CursorLockMode.Locked;
        Cursor.visible = false;
    }

    public void QuitGame()
    {
        Debug.Log("Quit Game");

#if UNITY_EDITOR
        UnityEditor.EditorApplication.isPlaying = false; // 在 Editor 關閉播放
#else
        Application.Quit(); // Build 後關閉遊戲
#endif
    }
}
