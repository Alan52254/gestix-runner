using UnityEngine;
using static UnityEngine.Rendering.DebugUI;

public class Coin : MonoBehaviour
{
    public float rotateSpeed = 90f;   // 旋轉速度（度/秒）
    public int value = 1;

    void Update()
    {
        // 讓金幣一直轉
        transform.Rotate(Vector3.up * rotateSpeed * Time.deltaTime, Space.World);
    }

    private void OnTriggerEnter(Collider other)
    {
        // 這裡假設你的角色 Tag 是 "Player"
        if (other.CompareTag("Player"))
        {
            // TODO：之後可以在這裡加分數或金幣計數
            Debug.Log("吃到金幣！");
            if (GameManager.Instance != null)
            {
                GameManager.Instance.AddCoin(value);  // ★ 撿金幣 → 通知 GameManager
            }
            Destroy(gameObject);
        }
    }
    
}
