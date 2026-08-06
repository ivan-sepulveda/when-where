import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";

export interface LightboxImage {
  src: string;
  caption: string;
}

interface CarouselLightboxProps {
  images: LightboxImage[];
  isOpen: boolean;
  onClose: () => void;
}

// Reusable image lightbox with prev/next navigation -- built for the
// Michelin card on DestinationDetail (see MICHELIN_CARD_BEHAVIOR there),
// but deliberately generic (just an images/isOpen/onClose prop, no
// Michelin-specific knowledge) so any other card that grows a photo set
// later can reuse it.
//
// Rendered through a portal straight onto document.body rather than
// inline where it's invoked -- that's what lets it visually sit above
// everything else on the page regardless of where in the DOM tree the
// triggering card lives, with no z-index/overflow fighting against
// ancestor elements.
export default function CarouselLightbox({ images, isOpen, onClose }: CarouselLightboxProps) {
  const [index, setIndex] = useState(0);
  const closeButtonRef = useRef<HTMLButtonElement>(null);
  const triggerElementRef = useRef<Element | null>(null);

  // Reset to the first slide, lock page scroll, and move focus into the
  // dialog every time it opens -- and restore focus to whatever
  // triggered it (the Michelin card's button) when it closes, so keyboard
  // users don't lose their place.
  useEffect(() => {
    if (!isOpen) return;

    setIndex(0);
    triggerElementRef.current = document.activeElement;
    closeButtonRef.current?.focus();

    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";

    return () => {
      document.body.style.overflow = previousOverflow;
      if (triggerElementRef.current instanceof HTMLElement) {
        triggerElementRef.current.focus();
      }
    };
  }, [isOpen]);

  // Escape closes; left/right arrow keys navigate, same as clicking the
  // on-screen prev/next buttons -- attached only while open.
  useEffect(() => {
    if (!isOpen) return;

    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
      if (e.key === "ArrowLeft") goToPrevious();
      if (e.key === "ArrowRight") goToNext();
    }

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isOpen, images.length]);

  if (!isOpen || images.length === 0) return null;

  // Wrap-around navigation (last -> first, first -> last) -- standard
  // lightbox/gallery behavior, avoids dead-ending the user at either end.
  function goToPrevious() {
    setIndex((current) => (current - 1 + images.length) % images.length);
  }

  function goToNext() {
    setIndex((current) => (current + 1) % images.length);
  }

  const current = images[index];

  return createPortal(
    <div className="lightbox-backdrop" onClick={onClose}>
      <div
        className="lightbox-dialog"
        role="dialog"
        aria-modal="true"
        aria-label={current.caption}
        // Stop clicks inside the dialog from bubbling to the backdrop's
        // onClick, which would otherwise close the lightbox any time the
        // user clicks the image, arrows, or caption.
        onClick={(e) => e.stopPropagation()}
      >
        <button type="button" className="lightbox-close-button" onClick={onClose} aria-label="Close">
          ✕
        </button>

        <div className="lightbox-image-area">
          {images.length > 1 && (
            <button
              type="button"
              className="lightbox-nav-button lightbox-nav-button-prev"
              onClick={goToPrevious}
              aria-label="Previous image"
            >
              ‹
            </button>
          )}

          <img src={current.src} alt={current.caption} className="lightbox-image" />

          {images.length > 1 && (
            <button
              type="button"
              className="lightbox-nav-button lightbox-nav-button-next"
              onClick={goToNext}
              aria-label="Next image"
            >
              ›
            </button>
          )}
        </div>

        <p className="lightbox-caption">{current.caption}</p>

        {images.length > 1 && (
          <div className="lightbox-dots">
            {images.map((image, i) => (
              <button
                key={image.src + i}
                type="button"
                className={`lightbox-dot${i === index ? " lightbox-dot-active" : ""}`}
                onClick={() => setIndex(i)}
                aria-label={`Go to image ${i + 1}`}
                aria-current={i === index}
              />
            ))}
          </div>
        )}
      </div>
    </div>,
    document.body,
  );
}
