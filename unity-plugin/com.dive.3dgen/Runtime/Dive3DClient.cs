using System;
using System.Collections;
using System.Text;
using UnityEngine;
using UnityEngine.Networking;

// Bypassa verificação SSL no Editor (desenvolvimento)
class BypassCert : CertificateHandler
{
    protected override bool ValidateCertificate(byte[] certificateData) => true;
}

namespace Dive.ThreeDGen
{
    /// <summary>
    /// Cliente HTTP que se comunica com o servidor Modal.
    /// Pode ser usado tanto em Editor quanto em Runtime.
    /// </summary>
    public class Dive3DClient
    {
        const float PollInterval = 2f;   // segundos entre checks de status
        const int   MaxPolls     = 300;  // timeout: 10 min

        readonly string _baseUrl;
        readonly string _apiKey;

        public Dive3DClient(string baseUrl, string apiKey)
        {
            _baseUrl = baseUrl.TrimEnd('/');
            _apiKey  = apiKey;
        }

        // ------------------------------------------------------------------ //
        // Ponto de entrada principal
        // ------------------------------------------------------------------ //

        /// <summary>
        /// Envia uma requisição de geração e aguarda o resultado.
        /// Chame via StartCoroutine.
        /// </summary>
        public IEnumerator Generate(
            GenerationRequest request,
            Action<GenerationJob> onComplete,
            Action<float, string> onProgress = null)
        {
            var job = new GenerationJob();

            // 1) Envia o job
            yield return SendGenerate(request, job);
            if (job.status == JobStatus.Error) { onComplete(job); yield break; }

            onProgress?.Invoke(0.05f, "Job enfileirado…");

            // 2) Polling de status
            int polls = 0;
            while (polls < MaxPolls)
            {
                yield return new WaitForSeconds(PollInterval);
                yield return PollStatus(job);

                polls++;
                float pct = Mathf.Clamp01(0.05f + polls / (float)MaxPolls * 0.90f);
                onProgress?.Invoke(pct, $"Gerando… ({polls * PollInterval:0}s)");

                if (job.status == JobStatus.Done || job.status == JobStatus.Error)
                    break;
            }

            if (job.status == JobStatus.Running)
            {
                job.status = JobStatus.Error;
                job.error  = "Timeout: o servidor demorou mais de 10 minutos.";
            }

            onComplete(job);
        }

        // ------------------------------------------------------------------ //
        // Internos
        // ------------------------------------------------------------------ //

        IEnumerator SendGenerate(GenerationRequest request, GenerationJob job)
        {
            var form = new WWWForm();
            form.AddField("model",   ModelToString(request.model));
            form.AddField("quality", request.quality.ToString().ToLower());

            if (!string.IsNullOrEmpty(request.prompt))
                form.AddField("prompt", request.prompt);

            if (request.imageBytes != null && request.imageBytes.Length > 0)
                form.AddBinaryData("image", request.imageBytes, "image.png", "image/png");

            using var www = UnityWebRequest.Post($"{_baseUrl}/generate", form);
            www.SetRequestHeader("X-API-Key", _apiKey);
            www.certificateHandler = new BypassCert();
            www.timeout = 60;

            yield return www.SendWebRequest();

            if (www.result != UnityWebRequest.Result.Success)
            {
                job.status = JobStatus.Error;
                job.error  = $"HTTP {www.responseCode} [{www.result}]: {www.error}\nURL: {_baseUrl}/generate";
                yield break;
            }

            var resp = JsonUtility.FromJson<GenerateResponse>(www.downloadHandler.text);
            job.jobId  = resp.job_id;
            job.status = JobStatus.Running;
        }

        IEnumerator PollStatus(GenerationJob job)
        {
            using var www = UnityWebRequest.Get($"{_baseUrl}/status/{job.jobId}");
            www.SetRequestHeader("X-API-Key", _apiKey);
            www.certificateHandler = new BypassCert();
            www.timeout = 30;

            yield return www.SendWebRequest();

            if (www.result != UnityWebRequest.Result.Success)
                yield break;   // Ignora erros de rede transitórios e tenta de novo

            var resp = JsonUtility.FromJson<StatusResponse>(www.downloadHandler.text);

            switch (resp.status)
            {
                case "done":
                    job.status   = JobStatus.Done;
                    job.glbBytes = Convert.FromBase64String(resp.glb_base64);
                    break;

                case "error":
                    job.status = JobStatus.Error;
                    job.error  = resp.detail ?? "Erro desconhecido no servidor.";
                    break;

                // "queued" / "running" → continua polling
            }
        }

        static string ModelToString(Model model) => model switch
        {
            Model.SF3D    => "sf3d",
            Model.TRELLIS => "trellis",
            Model.Hunyuan => "hunyuan",
            _             => "sf3d",
        };
    }
}
