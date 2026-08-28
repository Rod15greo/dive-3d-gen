using System.Threading.Tasks;
using GLTFast;
using UnityEngine;

namespace Dive.ThreeDGen
{
    /// <summary>
    /// Importa bytes de um arquivo .glb e instancia como GameObject na cena.
    /// Usa GLTFast (com.unity.cloud.gltfast), que é o importador oficial da Unity 6.
    /// </summary>
    public static class GlbImporter
    {
        /// <summary>
        /// Carrega bytes GLB e instancia o modelo como filho de <paramref name="parent"/>.
        /// Se <paramref name="parent"/> for null, instancia na raiz da cena.
        /// Retorna o GameObject criado, ou null em caso de falha.
        /// </summary>
        public static async Task<GameObject> ImportAsync(byte[] glbBytes, Transform parent = null, string name = "Generated3D")
        {
            var gltf = new GltfImport();
            bool success = await gltf.LoadGltfBinary(glbBytes);

            if (!success)
            {
                Debug.LogError("[Dive3DGen] Falha ao decodificar o arquivo GLB.");
                return null;
            }

            var root = new GameObject(name);
            if (parent != null)
                root.transform.SetParent(parent, worldPositionStays: false);

            var instantiator = new GameObjectInstantiator(gltf, root.transform);
            success = await gltf.InstantiateMainSceneAsync(instantiator);

            if (!success)
            {
                Debug.LogError("[Dive3DGen] Falha ao instanciar a cena GLB.");
                Object.DestroyImmediate(root);
                return null;
            }

            return root;
        }
    }
}
