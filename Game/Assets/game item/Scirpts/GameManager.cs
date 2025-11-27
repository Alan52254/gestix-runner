using UnityEngine;
using TMPro;
using UnityEngine.InputSystem;   // ★ 為了 PlayerInput
using UnityEngine.SceneManagement;


public class GameManager : MonoBehaviour
{
    public static GameManager Instance;

    // ================= 金幣 & 分數 =================
    [Header("金幣")]
    public int coinCount = 0;
    public TextMeshProUGUI coinText;

    [Header("分數")]
    public int score = 0;
    public TextMeshProUGUI scoreText;
    public int scorePerCoin = 10; // 每吃一個金幣加多少分

    // 主選單 & 遊戲流程 
    [Header("主選單")]
    public GameObject mainMenuPanel;  // MainMenuPanel

    [Header("設定畫面")]
    public GameObject settingsPanel;

    [Header("Game Over 畫面")]
    public GameObject GameOverPanel;

    [Header("玩家")]
    public PlayerInput playerInput;   // 玩家身上的 PlayerInput（ThirdPersonController 那顆）

    [Header("生成器")]
    public GameObject[] coinSpawners;    // 金幣生成器 GameObject
    public GameObject[] enemySpawners;   // 敵人生成器 GameObject






    private bool gameStarted = false;

    private void Awake()
    {
        if (Instance == null)
        {
            Instance = this;
        }
        else
        {
            Destroy(gameObject);
        }
    }

    public void OpenSettings()
    {
        // 主選單關掉，設定畫面打開
        if (mainMenuPanel != null) mainMenuPanel.SetActive(false);
        if (settingsPanel != null) settingsPanel.SetActive(true);
    }

    public void BackToMainMenu()
    {
        // 設定畫面關掉，主選單打開
        if (settingsPanel != null) settingsPanel.SetActive(false);
        if (mainMenuPanel != null) mainMenuPanel.SetActive(true);
    }


    private void Start()
    {
        // 一開始顯示滑鼠、解鎖游標（方便點選單）
        Cursor.lockState = CursorLockMode.None;
        Cursor.visible = true;

        // 一開始更新 UI（Coins / Score）
        UpdateUI();

        // 一開始還沒開始遊戲
        gameStarted = false;

        // 先關掉玩家操作
        if (playerInput != null)
            playerInput.enabled = false;

        // 先關閉所有生成器（不讓一開始就生敵人、金幣）
        foreach (var go in coinSpawners)
            if (go != null) go.SetActive(false);

        foreach (var go in enemySpawners)
            if (go != null) go.SetActive(false);

        // 顯示主選單 Panel
        if (mainMenuPanel != null)
            mainMenuPanel.SetActive(true);

        if (settingsPanel != null)
            settingsPanel.SetActive(false);

        if (GameOverPanel != null)
            GameOverPanel.SetActive(false);
    }

    



    // 金幣 & 分數 
    public void AddCoin(int value)
    {
        coinCount += value;        // 金幣數 +1（或其他數值）
        score += scorePerCoin;     // 分數增加
        UpdateUI();
    }

    private void UpdateUI()
    {
        if (coinText != null)
            coinText.text = $"Coins: {coinCount}";

        if (scoreText != null)
            scoreText.text = $"Score: {score}";
    }

    //開始遊戲 
    public void StartGame()
    {
        if (gameStarted) return;
        gameStarted = true;

        // 關掉主選單 UI
        if (mainMenuPanel != null)
            mainMenuPanel.SetActive(false);

        // 開始遊戲時鎖滑鼠、隱藏游標（方便操控視角）
        Cursor.lockState = CursorLockMode.Locked;
        Cursor.visible = false;

        // 開啟玩家操作
        if (playerInput != null)
            playerInput.enabled = true;

        // 打開金幣 / 敵人生成器（它們的 Start() 才會開始跑）
        foreach (var go in coinSpawners)
            if (go != null) go.SetActive(true);

        foreach (var go in enemySpawners)
            if (go != null) go.SetActive(true);

        Debug.Log("開始遊戲：玩家啟動，金幣與敵人開始生成");
    }

    public void GameOver()
    {
        Debug.Log("Game Over！");

        // 停止遊戲時間
        Time.timeScale = 0f;

        // 關閉玩家操作
        if (playerInput != null)
            playerInput.enabled = false;

        // 顯示滑鼠
        Cursor.lockState = CursorLockMode.None;
        Cursor.visible = true;

        // 顯示 Game Over 介面
        if (GameOverPanel != null)
            GameOverPanel.SetActive(true);
    }

    public void PlayAgain()
    {
        // 先把時間還原
        Time.timeScale = 1f;

        // 重新讀取目前場景
        Scene current = SceneManager.GetActiveScene();
        SceneManager.LoadScene(current.buildIndex);
    }

    public void QuitGame()
    {
        Debug.Log("Quit Game");

    #if UNITY_EDITOR
            UnityEditor.EditorApplication.isPlaying = false;  // 在 Editor 停止播放
    #else
        Application.Quit();  // Build 出去會關閉遊戲
    #endif
    }



}
