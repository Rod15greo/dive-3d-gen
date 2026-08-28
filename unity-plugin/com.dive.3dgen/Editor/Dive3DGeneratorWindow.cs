using System.IO;
using UnityEditor;
using UnityEngine;
using Dive.ThreeDGen;

namespace Dive.ThreeDGen.Editor
{
    /// <summary>
    /// Janela principal do Dive 3D Gen.
    /// Acesse via: Tools → Dive 3D Gen
    /// </summary>
    public class Dive3DGeneratorWindow : EditorWindow
    {
        // ------------------------------------------------------------------ //
        // Configurações (salvas nas EditorPrefs)
        // ------------------------------------------------------------------ //
        const string PrefUrl    = "Dive3DGen_ServerUrl";
        const string PrefApiKey = "Dive3DGen_ApiKey";

        string _serverUrl = "https://your-modal-url.modal.run";
        string _apiKey    = "";

        // ------------------------------------------------------------------ //
        // Formulário de geração
        // ------------------------------------------------------------------ //
        Model   _model   = Model.SF3D;
        Quality _quality = Quality.Balanced;
        string  _prompt  = "";
        Texture2D _referenceImage;

        // ------------------------------------------------------------------ //
        // Estado
        // ------------------------------------------------------------------ //
        bool   _isGenerating;
        float  _progress;
        string _progressMessage = "";
        string _lastError       = "";
        string _lastSavedPath   = "";

        // Coroutine runner (usa um MonoBehaviour temporário em Editor)
        EditorCoroutineRunner _runner;

        // ------------------------------------------------------------------ //
        // Menu
        // ------------------------------------------------------------------ //
        [MenuItem("Tools/Dive 3D Gen")]
        public static void ShowWindow()
        {
            var window = GetWindow<Dive3DGeneratorWindow>("Dive 3D Gen");
            window.minSize = new Vector2(380, 520);
        }

        // ------------------------------------------------------------------ //
        // Lifecycle
        // ------------------------------------------------------------------ //
        void OnEnable()
        {
            _serverUrl = EditorPrefs.GetString(PrefUrl,    _serverUrl);
            _apiKey    = EditorPrefs.GetString(PrefApiKey, _apiKey);
        }

        void OnDisable()
        {
            EditorPrefs.SetString(PrefUrl,    _serverUrl);
            EditorPrefs.SetString(PrefApiKey, _apiKey);
        }

        // ------------------------------------------------------------------ //
        // GUI
        // ------------------------------------------------------------------ //
        void OnGUI()
        {
            DrawHeader();
            DrawConfig();
            EditorGUILayout.Space(8);
            DrawForm();
            EditorGUILayout.Space(8);
            DrawGenerateButton();
            DrawProgress();
            DrawResult();
        }

        void DrawHeader()
        {
            EditorGUILayout.Space(6);
            var style = new GUIStyle(EditorStyles.boldLabel) { fontSize = 16, alignment = TextAnchor.MiddleCenter };
            EditorGUILayout.LabelField("🧊 Dive 3D Gen", style);
            EditorGUILayout.LabelField("Geração de assets 3D via IA", EditorStyles.centeredGreyMiniLabel);
            EditorGUILayout.Space(8);
        }

        void DrawConfig()
        {
            EditorGUILayout.LabelField("Configuração", EditorStyles.boldLabel);
            using (new EditorGUI.IndentLevelScope())
            {
                _serverUrl = EditorGUILayout.TextField("Server URL", _serverUrl);
                _apiKey    = EditorGUILayout.PasswordField("API Key",    _apiKey);
            }
        }

        void DrawForm()
        {
            EditorGUILayout.LabelField("Geração", EditorStyles.boldLabel);
            using (new EditorGUI.IndentLevelScope())
            {
                _model   = (Model)EditorGUILayout.EnumPopup("Modelo", _model);
                _quality = (Quality)EditorGUILayout.EnumPopup("Qualidade", _quality);

                EditorGUILayout.Space(4);

                // Prompt (não disponível para SF3D)
                using (new EditorGUI.DisabledScope(_model == Model.SF3D))
                {
                    EditorGUILayout.LabelField("Prompt (texto)");
                    _prompt = EditorGUILayout.TextArea(_prompt, GUILayout.Height(60));
                    if (_model == Model.SF3D)
                        EditorGUILayout.HelpBox("SF3D aceita apenas imagem.", MessageType.Info);
                }

                EditorGUILayout.Space(4);
                _referenceImage = (Texture2D)EditorGUILayout.ObjectField(
                    "Imagem de referência", _referenceImage, typeof(Texture2D), false);
            }
        }

        void DrawGenerateButton()
        {
            bool hasInput = !string.IsNullOrWhiteSpace(_prompt) || _referenceImage != null;
            bool canGenerate = !_isGenerating
                && !string.IsNullOrWhiteSpace(_serverUrl)
                && !string.IsNullOrWhiteSpace(_apiKey)
                && hasInput;

            using (new EditorGUI.DisabledScope(!canGenerate))
            {
                if (GUILayout.Button("⚡ Gerar 3D", GUILayout.Height(36)))
                    StartGeneration();
            }

            if (_isGenerating && GUILayout.Button("✖ Cancelar"))
                CancelGeneration();
        }

        void DrawProgress()
        {
            if (!_isGenerating && string.IsNullOrEmpty(_lastError)) return;

            EditorGUILayout.Space(6);

            if (_isGenerating)
            {
                EditorGUI.ProgressBar(EditorGUILayout.GetControlRect(false, 18), _progress, _progressMessage);
                Repaint();
            }

            if (!string.IsNullOrEmpty(_lastError))
                EditorGUILayout.HelpBox(_lastError, MessageType.Error);
        }

        void DrawResult()
        {
            if (string.IsNullOrEmpty(_lastSavedPath)) return;

            EditorGUILayout.Space(6);
            EditorGUILayout.HelpBox($"✅ Salvo em: {_lastSavedPath}", MessageType.None);

            if (GUILayout.Button("📂 Selecionar no Project"))
            {
                var asset = AssetDatabase.LoadAssetAtPath<Object>(_lastSavedPath);
                Selection.activeObject = asset;
                EditorGUIUtility.PingObject(asset);
            }

            if (GUILayout.Button("➕ Instanciar na cena"))
                InstantiateInScene();
        }

        // ------------------------------------------------------------------ //
        // Lógica de geração
        // ------------------------------------------------------------------ //
        void StartGeneration()
        {
            _isGenerating    = true;
            _progress        = 0f;
            _progressMessage = "Enviando…";
            _lastError       = "";
            _lastSavedPath   = "";

            var request = new GenerationRequest
            {
                model       = _model,
                quality     = _quality,
                prompt      = _prompt,
                imageBytes  = ReadImageBytes(_referenceImage),
            };

            var client = new Dive3DClient(_serverUrl, _apiKey);

            _runner = EditorCoroutineRunner.Start(
                client.Generate(
                    request,
                    OnGenerationComplete,
                    (pct, msg) => { _progress = pct; _progressMessage = msg; Repaint(); }
                )
            );
        }

        void CancelGeneration()
        {
            _runner?.Stop();
            _isGenerating    = false;
            _progressMessage = "";
            _lastError       = "Geração cancelada.";
            Repaint();
        }

        void OnGenerationComplete(GenerationJob job)
        {
            _isGenerating = false;

            if (job.status == JobStatus.Error)
            {
                _lastError = job.error;
                Repaint();
                return;
            }

            if (job.glbBytes == null || job.glbBytes.Length == 0)
            {
                _lastError = "Servidor retornou resposta vazia. Verifique os logs do Modal.";
                Repaint();
                return;
            }

            // Salva o GLB no projeto
            string dir = "Assets/Dive3DGen/Generated";
            Directory.CreateDirectory(dir);
            string filename  = $"Generated_{System.DateTime.Now:yyyyMMdd_HHmmss}.glb";
            string assetPath = $"{dir}/{filename}";
            File.WriteAllBytes(assetPath, job.glbBytes);
            AssetDatabase.Refresh();

            _lastSavedPath = assetPath;
            Repaint();
        }

        void InstantiateInScene()
        {
            if (string.IsNullOrEmpty(_lastSavedPath)) return;

            // Carrega via GameObject.Instantiate usando o prefab importado pelo GLTFast
            var asset = AssetDatabase.LoadAssetAtPath<GameObject>(_lastSavedPath);
            if (asset == null)
            {
                Debug.LogWarning("[Dive3DGen] Asset ainda não foi importado pelo GLTFast. Aguarde o import completar.");
                return;
            }
            var instance = (GameObject)PrefabUtility.InstantiatePrefab(asset);
            Selection.activeGameObject = instance;
            SceneView.FrameLastActiveSceneView();
        }

        static byte[] ReadImageBytes(Texture2D tex)
        {
            if (tex == null) return null;
            string path = AssetDatabase.GetAssetPath(tex);
            if (File.Exists(path)) return File.ReadAllBytes(path);
            return tex.EncodeToPNG();
        }
    }

    // ------------------------------------------------------------------ //
    // Helper: roda Coroutines dentro do Editor sem MonoBehaviour.
    // Suporta: IEnumerator aninhado, WaitForSeconds, yield return null.
    // ------------------------------------------------------------------ //
    internal class EditorCoroutineRunner
    {
        readonly System.Collections.Generic.Stack<System.Collections.IEnumerator> _stack
            = new System.Collections.Generic.Stack<System.Collections.IEnumerator>();
        double _waitUntil;
        AsyncOperation _pendingOp;
        bool _stopped;

        public static EditorCoroutineRunner Start(System.Collections.IEnumerator routine)
        {
            var runner = new EditorCoroutineRunner();
            runner._stack.Push(routine);
            EditorApplication.update += runner.Tick;
            return runner;
        }

        public void Stop()
        {
            _stopped = true;
            EditorApplication.update -= Tick;
        }

        void Tick()
        {
            if (_stopped || _stack.Count == 0) { Stop(); return; }

            // Aguarda WaitForSeconds
            if (EditorApplication.timeSinceStartup < _waitUntil) return;

            // Aguarda AsyncOperation (UnityWebRequest, etc.)
            if (_pendingOp != null)
            {
                if (!_pendingOp.isDone) return;
                _pendingOp = null;
            }

            var top = _stack.Peek();
            if (!top.MoveNext())
            {
                _stack.Pop();
                if (_stack.Count == 0) Stop();
                return;
            }

            var yielded = top.Current;

            if (yielded is System.Collections.IEnumerator nested)
            {
                _stack.Push(nested);
            }
            else if (yielded is AsyncOperation asyncOp)
            {
                // Espera a operação completar antes de avançar
                _pendingOp = asyncOp;
            }
            else if (yielded is WaitForSeconds wait)
            {
                var f = typeof(WaitForSeconds).GetField(
                    "m_Seconds",
                    System.Reflection.BindingFlags.NonPublic | System.Reflection.BindingFlags.Instance);
                float secs = f != null ? (float)f.GetValue(wait) : 1f;
                _waitUntil = EditorApplication.timeSinceStartup + secs;
            }
            // null: aguarda um frame
        }
    }
}
