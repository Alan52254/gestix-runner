using UnityEngine;

public class CoinSpawner : MonoBehaviour
{
    [Header("金幣設定")]
    public GameObject coinPrefab;         // 指定剛剛做好的 Coin prefab
    public int coinAmount = 20;           // 要生成幾顆金幣
    public float coinYOffset = 0.5f;      // 金幣離地面的高度

    [Header("隨機區域大小 (X,Z)")]
    public Vector3 areaSize = new Vector3(20f, 0f, 50f); // 區域長寬（以這個物件為中心）

    [Header("地板 Raycast 設定")]
    public float raycastHeight = 20f;     // 往下打射線的起始高度
    public LayerMask groundLayer;         // 地板所在的 Layer

    void Start()
    {
        SpawnCoins();
    }

    public void SpawnCoins()
    {
        for (int i = 0; i < coinAmount; i++)
        {
            Vector3 spawnPos;
            if (TryGetRandomPointOnGround(out spawnPos))
            {
                Instantiate(coinPrefab, spawnPos, Quaternion.identity);
            }
        }
    }

    bool TryGetRandomPointOnGround(out Vector3 result)
    {
        // 在區域內隨機一個 XZ 位置
        Vector3 randomOffset = new Vector3(
            Random.Range(-areaSize.x / 2f, areaSize.x / 2f),
            0f,
            Random.Range(-areaSize.z / 2f, areaSize.z / 2f)
        );

        Vector3 rayOrigin = transform.position + randomOffset + Vector3.up * raycastHeight;

        RaycastHit hit;
        if (Physics.Raycast(rayOrigin, Vector3.down, out hit, raycastHeight * 2f, groundLayer))
        {
            // 命中地板，回傳命中的位置再往上抬一點
            result = hit.point + Vector3.up * coinYOffset;
            return true;
        }

        result = Vector3.zero;
        return false;
    }

    // 方便在 Scene 視圖看到區域
    private void OnDrawGizmosSelected()
    {
        Gizmos.color = Color.yellow;
        Gizmos.DrawWireCube(transform.position, new Vector3(areaSize.x, 1f, areaSize.z));
    }
}
