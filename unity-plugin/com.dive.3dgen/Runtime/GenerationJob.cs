using System;

namespace Dive.ThreeDGen
{
    public enum JobStatus { Queued, Running, Done, Error }
    public enum Model { SF3D, TRELLIS, Hunyuan }
    public enum Quality { Fast, Balanced, High }

    [Serializable]
    public class GenerationRequest
    {
        public Model model = Model.SF3D;
        public Quality quality = Quality.Balanced;
        public string prompt;        // texto (TRELLIS / Hunyuan)
        public byte[] imageBytes;    // imagem PNG/JPG (qualquer modelo)
    }

    [Serializable]
    public class GenerationJob
    {
        public string jobId;
        public JobStatus status = JobStatus.Queued;
        public byte[] glbBytes;
        public string error;
        public DateTime startedAt = DateTime.UtcNow;
    }

    // Respostas da API
    [Serializable] internal class GenerateResponse { public string job_id; public string status; }
    [Serializable] internal class StatusResponse  { public string status; public string glb_base64; public string detail; }
}
