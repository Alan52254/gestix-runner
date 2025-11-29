using UnityEngine;

public class CoinSpawnerSimple : MonoBehaviour
{
    public GameObject coinPrefab;         // 金幣 prefab
    public int coinAmount = 20;           // 生成數量
    public Vector2 areaSize = new Vector2(20f, 20f); // 區域大小
    public float raycastHeight = 30f;     // 射線高度（從這麼高往下打）
    public float yOffset = 0.3f;          // 離地面一點點
    public LayerMask groundLayer;         // 設 Terrain 的 Layer

    void Start()
    {
        for (int i = 0; i < coinAmount; i++)
        {
            // 1. 隨機 XZ
            float randomX = Random.Range(-areaSize.x / 2f, areaSize.x / 2f);
            float randomZ = Random.Range(-areaSize.y / 2f, areaSize.y / 2f);

            Vector3 basePos = new Vector3(
                transform.position.x + randomX,
                transform.position.y,
                transform.position.z + randomZ
            );

            // 2. 從上往下 Raycast 找地板
            Vector3 rayOrigin = basePos + Vector3.up * raycastHeight;

            if (Physics.Raycast(rayOrigin, Vector3.down, out RaycastHit hit,
                                raycastHeight * 2f, groundLayer))
            {
                // 3. 命中地面 → 貼地生成
                Vector3 spawnPos = hit.point + Vector3.up * yOffset;
                Instantiate(coinPrefab, spawnPos, Quaternion.identity);
            }
        }
    }

    // Scene 視窗可視化生成範圍
    private void OnDrawGizmosSelected()
    {
        Gizmos.color = Color.yellow;
        Gizmos.DrawWireCube(transform.position,
            new Vector3(areaSize.x, 0.1f, areaSize.y));
    }
}
