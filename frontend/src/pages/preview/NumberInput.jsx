import styles from "./NumberInput.module.css"

export default function NumberInput(props) {
  let slider
  let number

  function onInput(evt) {
    slider.valueAsNumber = evt.target.valueAsNumber
    number.valueAsNumber = evt.target.valueAsNumber
    console.log(evt.target.valueAsNumber)
    props.onChange?.(evt.target.valueAsNumber)
  }

  const min = () => props.min ?? "0"
  const max = () => props.max ?? "1"
  const step = () => props.step ?? "0.1"

  return (
    <div class={styles.div}>
      <input
        ref={slider}
        type="range"
        name={props.name}
        value={props.value()}
        onInput={onInput}
        min={min()}
        max={max()}
        step={step()}
      />
      <input
        ref={number}
        onInput={onInput}
        value={props.value()}
        type="number"
        min={min()}
        max={max()}
        step={step()}
      />
    </div>
  )
}
