using TMPro;
using UnityEngine;
using UnityEngine.UI;   // 為了使用 Slider

public class PlayerHealth : MonoBehaviour
{
    [Header("血量設定")]
    public int maxHealth = 100;
    public int currentHealth;

    [Header("UI 元件")]
    public Slider healthSlider; // 血條 Slider
    public TextMeshProUGUI healthText;


    private void Start()
    {
        // 一開始血量全滿
        currentHealth = maxHealth;

        if (healthText == null && healthSlider != null)
        {
            healthText = healthSlider.GetComponentInChildren<TextMeshProUGUI>();
        }

        if (healthSlider != null)
        {
            healthSlider.maxValue = maxHealth;
            healthSlider.value = currentHealth;
        }
        UpdateHealthText();
    }

    // 呼叫這個函式來扣血
    public void TakeDamage(int damage)
    {
        currentHealth -= damage;
        if (currentHealth < 0)
            currentHealth = 0;

        if (healthSlider != null)
            healthSlider.value = currentHealth;
        UpdateHealthText();
        Debug.Log($"玩家受傷 -{damage}，目前 HP = {currentHealth}");

        if (currentHealth <= 0)
        {
            Die();
        }
    }
    private void UpdateHealthText()
    {
        if (healthText != null)
        {
            healthText.text = $"{currentHealth} / {maxHealth}";
        }
        else
        {
            Debug.LogWarning("[PlayerHealth] healthText 沒有指定！");
        }
    }

    void Die()
    {
        Debug.Log("玩家死亡");
        if (GameManager.Instance != null)
        {
            GameManager.Instance.GameOver();
        }
        else
        {
            Debug.LogWarning("[PlayerHealth] GameManager.Instance 是 null，請確認場景裡有 GameManager，且 Awake 有設定 Instance。");
        }
        // TODO：之後可以在這裡做
        // - 播放死亡動畫
        // - 顯示 Game Over 介面
        // - 停止玩家操作 / 重新載入場景
    }

    // 可選：恢復血量
    public void Heal(int amount)
    {
        currentHealth += amount;
        if (currentHealth > maxHealth)
            currentHealth = maxHealth;

        if (healthSlider != null)
            healthSlider.value = currentHealth;
    }
}
