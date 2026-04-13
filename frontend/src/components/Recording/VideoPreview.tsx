import { forwardRef, useEffect } from "react";

interface VideoPreviewProps {
  stream: MediaStream | null;
  muted?: boolean;
  src?: string;
}

const VideoPreview = forwardRef<HTMLVideoElement, VideoPreviewProps>(
  ({ stream, muted = true, src }, ref) => {
    useEffect(() => {
      const video = (ref as React.RefObject<HTMLVideoElement>)?.current;
      if (video && stream) {
        video.srcObject = stream;
      }
    }, [ref, stream]);

    return (
      <div className="relative aspect-video w-full rounded-2xl overflow-hidden border border-white/10 bg-black/60">
        <video
          ref={ref}
          autoPlay
          playsInline
          muted={muted}
          controls={!stream && Boolean(src)}
          src={src}
          className="w-full h-full object-cover"
        />
        {!stream && !src ? (
          <div className="absolute inset-0 flex items-center justify-center text-slate-400 text-sm">
            Camera preview will appear here
          </div>
        ) : null}
      </div>
    );
  }
);

VideoPreview.displayName = "VideoPreview";
export default VideoPreview;
