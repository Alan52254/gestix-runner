using UnityEngine;

public class EnemySpawner : MonoBehaviour
{
    public GameObject enemyPrefab;    // 敵人 Prefab
    public Transform player;          // 玩家
    public float spawnRadius = 15f;   // 距玩家多遠出生
    public float spawnInterval = 5f;  // 幾秒生一次

    [Header("貼地設定")]
    public LayerMask groundLayer;     // Terrain 用的 Ground Layer
    public float raycastHeight = 30f; // 射線起始高度
    public float yOffset = 0.1f;      // 讓敵人稍微浮離地面一點

    private float _timer;

    void Update()
    {
        if (player == null) return;

        _timer += Time.deltaTime;
        if (_timer >= spawnInterval)
        {
            _timer = 0f;
            SpawnEnemyOnGround();
        }
    }

    void SpawnEnemyOnGround()
    {
        // 1. 隨機一個方向 & 距離（在玩家周圍的一個圓上）
        Vector2 randomCircle = Random.insideUnitCircle.normalized * spawnRadius;
        Vector3 basePos = new Vector3(
            player.position.x + randomCircle.x,
            player.position.y,
            player.position.z + randomCircle.y
        );

        // 2. 從上往下打 Raycast 去找地板
        Vector3 rayOrigin = basePos + Vector3.up * raycastHeight;

        if (Physics.Raycast(rayOrigin, Vector3.down, out RaycastHit hit,
                            raycastHeight * 2f, groundLayer))
        {
            // 3. 命中地板，把敵人生成在 hit.point 上（再抬一點點）
            Vector3 spawnPos = hit.point + Vector3.up * yOffset;
            Instantiate(enemyPrefab, spawnPos, Quaternion.identity);
        }
        else
        {
            // 沒打到地板就略過這次，避免生在奇怪地方
            Debug.LogWarning("EnemySpawner：這次沒打到 Ground，沒有生成敵人");
        }
    }

    private void OnDrawGizmosSelected()
    {
        if (player == null) return;
        Gizmos.color = Color.red;
        Gizmos.DrawWireSphere(player.position, spawnRadius);
    }
}
