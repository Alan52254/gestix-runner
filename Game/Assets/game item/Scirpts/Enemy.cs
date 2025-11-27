using UnityEngine;

public class Enemy : MonoBehaviour
{
    public float moveSpeed = 10f;        // 追蹤速度
    public LayerMask groundLayer;      // 地板的 Layer（跟你 Spawn 時用的一樣）
    public float groundRayHeight = 5f; // 往下打射線的高度
    public float groundOffset = 0.1f;  // 稍微浮在地板上
    public float stopDistance = 1.0f;   // 離玩家多近就不硬貼上去
    public int damage = 20;   // 撞到玩家扣多少血
    private Transform target;           // 玩家
    private Animator animator;          // 動畫控制器

    void Start()
    {
        // 找玩家
        GameObject player = GameObject.FindGameObjectWithTag("Player");
        if (player != null)
        {
            target = player.transform;
        }
        else
        {
            Debug.LogWarning("找不到 Tag=Player 的物件");
        }

        // 取得 Animator
        animator = GetComponent<Animator>();
    }

    void Update()
    {
        if (target == null) return;

        // 只在水平面追
        Vector3 targetPos = target.position;
        targetPos.y = transform.position.y;

        Vector3 dir = targetPos - transform.position;
        float distance = dir.magnitude;

        bool isMoving = false;

        if (distance > stopDistance)
        {
            dir.Normalize();
            transform.position += dir * moveSpeed * Time.deltaTime;
            transform.LookAt(targetPos);
            isMoving = true;
        }
        // 2. 用 Raycast 往下貼 terrain 高度
        StickToGround();

        // ★ 控制動畫
        if (animator != null)
        {
            // StarterAssets 的 ThirdPersonController 通常用這幾個參數
            animator.SetBool("Grounded", true);
            animator.SetFloat("MotionSpeed", 1f);

            if (isMoving)
                animator.SetFloat("Speed", moveSpeed);  // >0 就會播走路/跑步
            else
                animator.SetFloat("Speed", 0f);         // 0 就是 Idle
        }
    }

    void StickToGround()
    {
        if (Terrain.activeTerrain == null) return;

        Vector3 pos = transform.position;
        float terrainY = Terrain.activeTerrain.SampleHeight(pos)
                         + Terrain.activeTerrain.transform.position.y;

        pos.y = terrainY + groundOffset;
        transform.position = pos;
    }



    private void OnTriggerEnter(Collider other)
    {
        if (other.CompareTag("Player"))
        {
            // 找玩家身上的 PlayerHealth
            PlayerHealth hp = other.GetComponent<PlayerHealth>();
            if (hp != null)
            {
                hp.TakeDamage(20);
            }

            Debug.Log("玩家碰到敵人，扣血並刪除敵人");
            Destroy(gameObject);
        }
    }
}
